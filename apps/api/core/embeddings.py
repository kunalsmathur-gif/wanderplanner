from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from core.config import settings

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder, SentenceTransformer

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None
_reranker: CrossEncoder | None = None
# Guards the lazy singleton init below. Without this, the *first* request
# that needs embeddings — which in practice is usually a feasibility check
# or itinerary generation, both of which fan out to several concurrent
# `asyncio.to_thread(embed, ...)` calls via `asyncio.gather` — can enter
# `get_embedder()`/`get_reranker()` from more than one OS thread at once,
# all seeing `_model is None` before any of them finishes constructing it.
# That's not just wasted duplicate work: reproduced locally, concurrent
# `SentenceTransformer(...)`/`CrossEncoder(...)` construction from multiple
# threads corrupts the local HF Hub cache read (the model's own on-disk
# cache-lock file is not safe against this apparently), so one of the
# racing loads silently decides the model "doesn't exist" locally at all,
# falls back to a live download, and (whether or not that live download can
# even succeed) can still blow up with `NotImplementedError: Cannot copy
# out of meta tensor; no data!` from torch's device-placement code. A plain
# lock serializes construction so only the first caller ever loads the
# model; every other caller (concurrent or not) just reuses the singleton.
_model_lock = threading.Lock()
_reranker_lock = threading.Lock()


def _load_local_first(loader, model_name: str):
    """Load a sentence-transformers model, preferring the on-disk HF cache.

    By default sentence-transformers/huggingface_hub does a live network
    check (HEAD request) against huggingface.co on every load, even when a
    complete cached copy already exists locally — these are small, pinned
    models we always expect to already be cached (first-run/deploy aside).
    Under any network hiccup reaching huggingface.co (blocked egress, DNS,
    or — as reproduced locally on a machine with TLS-intercepting corporate
    proxy — a cert failure), huggingface_hub retries that HEAD check up to
    5x with exponential backoff before falling back to the cache anyway,
    turning what should be an instant local load into a 60-100s+ stall on
    every cold process start (including every redeploy, since each restarts
    these module-level singletons from scratch). That stall was hitting
    downstream request timeouts (e.g. the frontend's feasibility-check
    call) well before the model ever got a chance to load.

    `local_files_only=True` skips that network check entirely and loads
    straight from cache. Falls back to a normal (network-allowed) load only
    if that raises — e.g. a genuinely fresh environment where the model
    hasn't been cached yet at all."""
    try:
        return loader(model_name, device="cpu", local_files_only=True)
    except Exception:
        logger.info(
            "%s not found in local cache (or local-only load failed) — "
            "falling back to a network-allowed load.", model_name,
        )
        return loader(model_name, device="cpu")


def get_embedder():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:  # re-check: another thread may have won the race
                try:
                    from sentence_transformers import SentenceTransformer as ST
                    # Force CPU: these are small models where GPU offers little
                    # benefit locally, and calls are offloaded to a worker
                    # thread (see embed() callers using asyncio.to_thread) to
                    # keep the event loop free. PyTorch's MPS (Apple GPU)
                    # backend is not thread-safe when invoked off the main
                    # thread — it crashes/hangs the whole process — so we
                    # must not let SentenceTransformer auto-select "mps" here.
                    _model = _load_local_first(ST, settings.embedding_model)
                except ImportError:
                    raise RuntimeError(
                        "sentence-transformers not installed. "
                        "Run: pip install -r requirements-ml.txt"
                    )
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    model = get_embedder()
    return model.encode(texts, batch_size=64, show_progress_bar=False).tolist()


def get_reranker():
    """Lazily load the cross-encoder reranker model (docs §P3).

    Kept separate from the bi-encoder embedder: a CrossEncoder scores a
    (query, document) pair jointly, which is far more precise than comparing
    two independently-embedded vectors — but it's O(n) forward passes per
    query, so it's only used to rerank a small shortlist, not full retrieval.
    """
    global _reranker
    if _reranker is None:
        with _reranker_lock:
            if _reranker is None:  # re-check: another thread may have won the race
                try:
                    from sentence_transformers import CrossEncoder
                    # Same MPS-off-main-thread crash risk as the embedder,
                    # plus the same concurrent-first-load race — see the
                    # `_model_lock` comment above.
                    _reranker = _load_local_first(CrossEncoder, settings.reranker_model)
                except ImportError:
                    raise RuntimeError(
                        "sentence-transformers not installed. "
                        "Run: pip install -r requirements-ml.txt"
                    )
    return _reranker


def rerank_scores(query: str, texts: list[str]) -> list[float]:
    """Return cross-encoder relevance scores for `query` against each of `texts`."""
    if not texts:
        return []
    model = get_reranker()
    pairs = [(query, text) for text in texts]
    return model.predict(pairs).tolist()
