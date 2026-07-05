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
            _model = ST(settings.embedding_model)
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
            _reranker = CrossEncoder(settings.reranker_model)
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
