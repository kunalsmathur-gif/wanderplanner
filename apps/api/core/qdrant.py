from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from core.config import settings

_client: QdrantClient | None = None


def get_qdrant() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
        _ensure_collections(_client)
    return _client


def _ensure_collections(client: QdrantClient):
    collections = {
        settings.qdrant_collection_wiki: 384,
        settings.qdrant_collection_reddit: 384,
        settings.qdrant_collection_osm: 384,
    }
    existing = {c.name for c in client.get_collections().collections}
    for name, dim in collections.items():
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
