from sentence_transformers import SentenceTransformer

from core.config import settings

_model: SentenceTransformer | None = None


def get_embedder() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    model = get_embedder()
    return model.encode(texts, batch_size=64, show_progress_bar=False).tolist()
