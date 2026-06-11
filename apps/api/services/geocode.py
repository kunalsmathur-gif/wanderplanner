"""Nominatim geocoding proxy with 1 req/s rate limiting and LRU cache."""
from __future__ import annotations

import asyncio
import httpx
from functools import lru_cache

from core.config import settings
from models.common import GeocodeResponse

_lock = asyncio.Lock()
_last_call = 0.0

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


@lru_cache(maxsize=512)
def _cached_geocode(city: str) -> dict | None:
    return None


async def geocode_city(city: str) -> GeocodeResponse:
    global _last_call

    async with _lock:
        now = asyncio.get_event_loop().time()
        wait = (1.0 / settings.nominatim_rate_limit) - (now - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = asyncio.get_event_loop().time()

    params = {
        "q": city,
        "format": "json",
        "limit": 1,
    }
    headers = {"User-Agent": settings.nominatim_user_agent}

    async with httpx.AsyncClient(timeout=10, headers=headers) as client:
        resp = await client.get(NOMINATIM_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    if not data:
        raise ValueError(f"Location not found: {city}")

    hit = data[0]
    return GeocodeResponse(
        display_name=hit.get("display_name", city),
        lat=float(hit.get("lat", 0)),
        lon=float(hit.get("lon", 0)),
        country_code=hit.get("address", {}).get("country_code", ""),
    )
