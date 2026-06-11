from __future__ import annotations

from typing import TYPE_CHECKING

from core.config import settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None


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
