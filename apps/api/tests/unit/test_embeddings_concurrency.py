"""Pins the fix for a real production-shaped bug: the first request that
needs embeddings (a feasibility check or itinerary generation) fans out to
several concurrent `asyncio.to_thread(embed, ...)` calls, so on a cold
process (right after a deploy/restart) more than one OS thread can enter
`get_embedder()`/`get_reranker()` at once, all seeing the singleton as
`None`.

Reproduced live: concurrent `SentenceTransformer(...)`/`CrossEncoder(...)`
construction from multiple threads corrupted the local HF Hub cache read,
causing one racing load to decide the (fully-cached) model "doesn't exist"
locally at all and fall back to a live download — which could itself still
raise `NotImplementedError: Cannot copy out of meta tensor; no data!` from
torch's device-placement code. On the machine this was found on, the live
download path was also blocked by a corporate TLS-intercepting proxy, so
every retry added multi-second backoff on top — turning a request that
should take a couple of seconds into one that took 90-100+ seconds and blew
past the frontend's request timeout, exactly matching a "feasibility check
failing multiple times" report.

These tests don't require the real ML dependencies or network access — they
swap in cheap fake loaders via `core.embeddings._load_local_first` and the
module's raw `_model`/`_reranker` globals, and assert only the concurrency
contract: the underlying loader is invoked exactly once no matter how many
threads race to get the singleton first.
"""
from __future__ import annotations

import threading

import core.embeddings as embeddings_module


class _FakeModel:
    """Stand-in for a loaded SentenceTransformer/CrossEncoder — slow enough
    on first construction to make a real race between threads likely if the
    lock weren't there, and identifiable so we can assert every caller got
    the exact same instance back."""

    def __init__(self):
        import time
        time.sleep(0.05)


def _make_call_counting_loader():
    """A `loader(model_name, device=..., local_files_only=...)`-shaped
    callable that counts how many times it was actually invoked, so the
    test can assert the model is constructed exactly once even under a
    concurrent stampede of first callers."""
    calls = []
    lock = threading.Lock()

    def loader(model_name, device=None, local_files_only=False):
        with lock:
            calls.append((model_name, device, local_files_only))
        return _FakeModel()

    return loader, calls


class TestGetEmbedderConcurrency:
    def setup_method(self):
        embeddings_module._model = None

    def teardown_method(self):
        embeddings_module._model = None

    def test_concurrent_first_callers_construct_the_model_exactly_once(self, monkeypatch):
        loader, calls = _make_call_counting_loader()
        # Patch the loader `_load_local_first` calls, not `_load_local_first`
        # itself, so the real check-then-set-under-lock logic in
        # `get_embedder()` (the thing this test exists to pin) still runs.
        monkeypatch.setattr(
            embeddings_module, "_load_local_first",
            lambda _loader, model_name: loader(model_name, device="cpu", local_files_only=True),
        )

        results = []
        errors = []

        def worker():
            try:
                results.append(embeddings_module.get_embedder())
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(calls) == 1, "model constructor must run exactly once even under a concurrent stampede"
        assert len(results) == 8
        assert all(r is results[0] for r in results), "every caller must receive the same singleton instance"


class TestGetRerankerConcurrency:
    def setup_method(self):
        embeddings_module._reranker = None

    def teardown_method(self):
        embeddings_module._reranker = None

    def test_concurrent_first_callers_construct_the_reranker_exactly_once(self, monkeypatch):
        loader, calls = _make_call_counting_loader()
        monkeypatch.setattr(
            embeddings_module, "_load_local_first",
            lambda _loader, model_name: loader(model_name, device="cpu", local_files_only=True),
        )

        results = []
        errors = []

        def worker():
            try:
                results.append(embeddings_module.get_reranker())
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(calls) == 1, "reranker constructor must run exactly once even under a concurrent stampede"
        assert len(results) == 8
        assert all(r is results[0] for r in results), "every caller must receive the same singleton instance"


class TestLoadLocalFirst:
    def test_prefers_local_files_only_when_it_succeeds(self):
        calls = []

        def loader(model_name, device=None, local_files_only=False):
            calls.append(local_files_only)
            return _FakeModel()

        embeddings_module._load_local_first(loader, "some/model")

        assert calls == [True], "must attempt local_files_only=True first, and not fall back if it succeeds"

    def test_falls_back_to_network_allowed_load_if_local_only_raises(self):
        calls = []

        def loader(model_name, device=None, local_files_only=False):
            calls.append(local_files_only)
            if local_files_only:
                raise OSError("not cached locally")
            return _FakeModel()

        result = embeddings_module._load_local_first(loader, "some/model")

        assert calls == [True, False], "must fall back to a network-allowed load only after local-only fails"
        assert isinstance(result, _FakeModel)
