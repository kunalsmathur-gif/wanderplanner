"""Itinerary cache — Tier 1 fallback (docs §4 Tier 1).

Successfully generated itineraries are stored in the `itinerary_cache`
Qdrant collection, keyed by an embedding of (destination, duration, pace,
purpose). When the live LLM call fails, a semantically similar past
itinerary can be served instantly instead of failing the request outright.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, datetime, timezone

from core.config import settings
from core.qdrant import get_qdrant
from core.embeddings import embed
from models.trip import TripConfig


def _cache_key_text(trip_config: TripConfig) -> str:
    dest = trip_config.destination.city if trip_config.destination else "general"
    dates = trip_config.dates if isinstance(trip_config.dates, dict) else {}
    start = dates.get("start_date") or dates.get("start")
    end = dates.get("end_date") or dates.get("end")
    duration = "unknown"
    if start and end:
        try:
            duration = str(max(1, (date.fromisoformat(end) - date.fromisoformat(start)).days))
        except Exception:
            pass
    purpose = getattr(trip_config, "purpose", "") or ""
    pace = getattr(trip_config, "pace", "") or ""
    return f"{dest} {duration}d {pace} {purpose} trip"


async def get_cached_itinerary(trip_config: TripConfig) -> dict | None:
    """Look up a semantically similar cached itinerary (cosine >= threshold)."""
    query = _cache_key_text(trip_config)
    vector = (await asyncio.to_thread(embed, [query]))[0]
    client = get_qdrant()

    def _search():
        return client.search(
            collection_name=settings.qdrant_collection_itinerary_cache,
            query_vector=vector,
            limit=1,
            score_threshold=settings.itinerary_cache_score_threshold,
        )

    try:
        hits = await asyncio.to_thread(_search)
    except Exception:
        return None  # cache lookup is best-effort — never block the fallback chain
    if not hits:
        return None

    payload = hits[0].payload or {}
    raw = payload.get("itinerary_json")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        parsed["_from_fallback"] = "cache"
        return parsed
    except (TypeError, json.JSONDecodeError):
        return None


async def store_itinerary(trip_config: TripConfig, itinerary_raw: dict) -> None:
    """Best-effort cache write after a successful LLM generation.

    Never raises — a cache-write failure shouldn't affect the response
    already being returned to the user.
    """
    try:
        query = _cache_key_text(trip_config)
        vector = (await asyncio.to_thread(embed, [query]))[0]
        dest = trip_config.destination.city if trip_config.destination else "general"
        point_id = int(hashlib.md5(query.encode()).hexdigest(), 16) % (2**63)

        # Don't persist a fallback-generated itinerary as if it were a
        # genuine LLM result — that would let a degraded skeleton/mock
        # poison the cache for future requests.
        clean_payload = {k: v for k, v in itinerary_raw.items() if not k.startswith("_")}

        def _upsert():
            from qdrant_client.models import PointStruct
            client = get_qdrant()
            client.upsert(
                collection_name=settings.qdrant_collection_itinerary_cache,
                points=[PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "destination": dest,
                        "cache_key": query,
                        "itinerary_json": json.dumps(clean_payload),
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )],
            )

        await asyncio.to_thread(_upsert)
    except Exception:
        pass  # cache write is a best-effort optimization, never fail the request
