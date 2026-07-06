"""Pexels API client — fetches a single relevant hero photo per itinerary day.

Best-effort / non-critical: any failure (missing key, network error, no
results) returns None rather than raising, so a photo-fetch problem never
breaks itinerary generation.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from core.config import settings

_log = logging.getLogger(__name__)

_SEARCH_URL = "https://api.pexels.com/v1/search"

# Tiny in-memory cache (per-process) so repeated queries (e.g. the same
# destination/theme across users or re-generations) don't re-hit the API.
_cache: dict[str, dict | None] = {}
_CACHE_MAX_SIZE = 500


async def get_day_photo(query: str) -> dict | None:
    """Return {"url", "photographer", "photographer_url"} for the best-match
    landscape photo for `query`, or None if unavailable."""
    query = (query or "travel destination").strip()
    if not settings.pexels_api_key:
        return None

    if query in _cache:
        return _cache[query]

    result: dict | None = None
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(
                _SEARCH_URL,
                headers={"Authorization": settings.pexels_api_key},
                params={"query": query, "per_page": 1, "orientation": "landscape"},
            )
            resp.raise_for_status()
            data = resp.json()
            photos = data.get("photos") or []
            if photos:
                photo = photos[0]
                result = {
                    "url": photo.get("src", {}).get("large") or photo.get("src", {}).get("medium", ""),
                    "photographer": photo.get("photographer", ""),
                    "photographer_url": photo.get("photographer_url", ""),
                }
    except Exception as exc:
        _log.warning("Pexels photo fetch failed for query %r: %s", query, exc)
        result = None

    if len(_cache) >= _CACHE_MAX_SIZE:
        _cache.clear()
    _cache[query] = result
    return result


async def get_day_photos(queries: list[str]) -> list[dict | None]:
    """Fetch photos for multiple queries concurrently."""
    return await asyncio.gather(*(get_day_photo(q) for q in queries))
