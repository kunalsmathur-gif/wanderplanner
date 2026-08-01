"""`sentence-transformers` must reach the production image.

The trade this guards: CI does not install `requirements-ml.txt` (~3GB with
PyTorch), and the RAG tests stub the models instead, so **nothing in CI ever
imports sentence-transformers**. That is fine for test speed but removes the
check that used to exist by accident — and this project has already shipped a
production image without it once, which broke itinerary generation end-to-end
(`core/embeddings.py::get_embedder()` backs both the primary Gemini retrieval
path and its fallback chain).

These are file-content assertions on purpose: they cost milliseconds, need no
ML install, and fail loudly the moment the Dockerfile and the requirements
file drift apart.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_API_ROOT = Path(__file__).resolve().parents[2]
_DOCKERFILE = _API_ROOT / "Dockerfile"
_REQUIREMENTS_ML = _API_ROOT / "requirements-ml.txt"

_PIN_RE = re.compile(r"sentence-transformers==([0-9][^\s\"']*)")


def _pinned_version(text: str) -> str | None:
    match = _PIN_RE.search(text)
    return match.group(1) if match else None


@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    assert _DOCKERFILE.is_file(), f"expected a Dockerfile at {_DOCKERFILE}"
    return _DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def requirements_ml_text() -> str:
    assert _REQUIREMENTS_ML.is_file(), f"expected {_REQUIREMENTS_ML}"
    return _REQUIREMENTS_ML.read_text(encoding="utf-8")


def test_dockerfile_installs_sentence_transformers(dockerfile_text: str):
    """Without this the container starts fine and then fails on the first
    itinerary — the worst shape of failure, since /health stays green."""
    assert _pinned_version(dockerfile_text) is not None, (
        "The production Dockerfile must install sentence-transformers. "
        "core/embeddings.py needs it for both the primary retrieval path and "
        "the RAG fallback chain, so omitting it breaks generation at runtime "
        "while the image still builds and passes its healthcheck."
    )


def test_dockerfile_pin_matches_requirements_ml(
    dockerfile_text: str, requirements_ml_text: str
):
    """The Dockerfile installs this one package directly rather than the whole
    heavy file, so the two pins are maintained separately and can silently
    diverge — meaning local/eval and production would run different model code."""
    docker_pin = _pinned_version(dockerfile_text)
    requirements_pin = _pinned_version(requirements_ml_text)

    assert requirements_pin is not None, (
        "requirements-ml.txt no longer pins sentence-transformers"
    )
    assert docker_pin == requirements_pin, (
        f"sentence-transformers pin drift: Dockerfile has {docker_pin!r}, "
        f"requirements-ml.txt has {requirements_pin!r}. Update both together."
    )
