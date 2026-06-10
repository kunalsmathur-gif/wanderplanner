"""Semantic search service — queries Qdrant collections."""
from qdrant_client.models import Filter, FieldCondition, MatchValue

from core.config import settings
from core.qdrant import get_qdrant
from core.embeddings import embed
from models.common import SearchResult
from models.trip import TripConfig


async def semantic_search(
    query: str, destination: str, limit: int = 10
) -> list[SearchResult]:
    vector = embed([query])[0]
    client = get_qdrant()

    dest_filter = Filter(
        must=[FieldCondition(key="destination", match=MatchValue(value=destination))]
    )

    results = []
    for collection in [settings.qdrant_collection_wiki, settings.qdrant_collection_reddit]:
        hits = client.search(
            collection_name=collection,
            query_vector=vector,
            query_filter=dest_filter,
            limit=limit // 2,
        )
        for hit in hits:
            p = hit.payload or {}
            results.append(SearchResult(
                text=p.get("text", p.get("text_preview", "")),
                source=p.get("source", collection),
                source_url=p.get("source_url", p.get("post_url", "")),
                score=hit.score,
                destination=p.get("destination", destination),
            ))

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]


async def retrieve_context(trip_config: TripConfig) -> list[dict]:
    """Retrieve top-20 context chunks for itinerary generation."""
    dest = trip_config.destination.city if trip_config.destination else "general"
    persona_keywords = " ".join(trip_config.personas).replace("_", " ")
    query = f"{dest} travel {persona_keywords} highlights activities food"

    results = await semantic_search(query, dest, limit=20)
    return [{"text": r.text, "source": r.source, "url": r.source_url} for r in results]
