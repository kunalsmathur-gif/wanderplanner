from __future__ import annotations

from typing import TYPE_CHECKING

from core.config import settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer, CrossEncoder

_model: SentenceTransformer | None = None
_reranker: CrossEncoder | None = None


def get_embedder():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer as ST
            # Force CPU: these are small models where GPU offers little benefit
            # locally, and calls are offloaded to a worker thread (see embed()
            # callers using asyncio.to_thread) to keep the event loop free.
            # PyTorch's MPS (Apple GPU) backend is not thread-safe when invoked
            # off the main thread — it crashes/hangs the whole process — so we
            # must not let SentenceTransformer auto-select "mps" here.
            _model = ST(settings.embedding_model, device="cpu")
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
        try:
            from sentence_transformers import CrossEncoder
            # Same MPS-off-main-thread crash risk as the embedder — force CPU.
            _reranker = CrossEncoder(settings.reranker_model, device="cpu")
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
