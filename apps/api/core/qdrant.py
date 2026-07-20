from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    VectorParams,
)

from core.config import settings

_client: QdrantClient | None = None

# Collections that get filtered/scrolled by the "destination" payload field
# (services/search.py, services/gems.py, services/rag_fallback.py). Qdrant
# Cloud (unlike the :memory: mode used for local dev) rejects filtered
# queries on a field with no payload index — a 400 "Index required but not
# found" — so every one of these needs an explicit keyword index. This was
# silently breaking RAG context retrieval in production after the Cloud
# migration (2026-07-15) since :memory: doesn't enforce the requirement and
# nothing had exercised a real filtered query against the Cloud cluster
# until this was caught (2026-07-16).
_DESTINATION_INDEXED_COLLECTIONS = (
    "qdrant_collection_wiki",
    "qdrant_collection_reddit",
    "qdrant_collection_osm",
    "qdrant_collection_itinerary_corpus",
)


def get_qdrant() -> QdrantClient:
    global _client
    if _client is None:
        if settings.qdrant_url == ":memory:":
            # In-memory mode for local dev — no Docker needed
            _client = QdrantClient(":memory:")
        else:
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
        settings.qdrant_collection_itinerary_cache: 384,
    }
    existing = {c.name for c in client.get_collections().collections}
    for name, dim in collections.items():
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    # itinerary_corpus (docs/rag-strategy.md §9) uses two NAMED vectors per
    # point — "config" (destination+duration+pace+purpose+budget_tier+group
    # embedding, retrieved by matching the requesting user's trip config) and
    # "content" (full day-by-day text, retrieved by semantic content
    # similarity) — rather than a single vector, per the documented
    # config+content dual-embedding retrieval strategy.
    if settings.qdrant_collection_itinerary_corpus not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection_itinerary_corpus,
            vectors_config={
                "config": VectorParams(size=384, distance=Distance.COSINE),
                "content": VectorParams(size=384, distance=Distance.COSINE),
            },
        )

    for setting_name in _DESTINATION_INDEXED_COLLECTIONS:
        collection_name = getattr(settings, setting_name)
        info = client.get_collection(collection_name)
        if "destination" not in (info.payload_schema or {}):
            client.create_payload_index(
                collection_name=collection_name,
                field_name="destination",
                field_schema=PayloadSchemaType.KEYWORD,
            )


def delete_stale_destination_points(
    client: QdrantClient, collection_name: str, destination: str, keep_ids: set[int]
) -> int:
    """Delete any points for `destination` in `collection_name` whose ID isn't
    in `keep_ids`.

    Ingestion upserts by a stable hash of (destination, name)/(url, section,
    text) — safe for re-running unchanged logic, but when the
    category-selection/chunking logic itself changes, points dropped by the
    new logic are never deleted, only new ones added (live-confirmed
    2026-07-20: re-ingesting London's OSM POIs with the round-robin fix left
    the old all-food/drink points in place, doubling the collection to 112
    and diluting services/poi_pinning.py's fuzzy-name matching). Call this
    right before upserting a fresh ingestion run's points so each re-ingest
    is effectively delete-then-upsert per destination, not append-only.

    Returns the number of stale points deleted.
    """
    stale_ids: list[int] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(must=[FieldCondition(key="destination", match=MatchValue(value=destination))]),
            limit=256,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        stale_ids.extend(p.id for p in points if p.id not in keep_ids)
        if offset is None:
            break

    if stale_ids:
        client.delete(collection_name=collection_name, points_selector=stale_ids)
    return len(stale_ids)
