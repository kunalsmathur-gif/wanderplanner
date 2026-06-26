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
def _cached_geocode(city: str, lang: str = "en") -> dict | None:
    return None


async def geocode_city(city: str, countrycodes: str = "") -> GeocodeResponse:
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
        "addressdetails": 1,
        "namedetails": 1,       # request English name details
    }
    if countrycodes:
        params["countrycodes"] = countrycodes
    headers = {
        "User-Agent": settings.nominatim_user_agent,
        "Accept-Language": "en",  # force English names from Nominatim
    }

    async with httpx.AsyncClient(timeout=10, headers=headers) as client:
        resp = await client.get(NOMINATIM_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    if not data:
        raise ValueError(f"Location not found: {city}")

    hit = data[0]

    # Resolve English city name: prefer namedetails["name:en"] > address["city"|"town"|"village"] > display_name first segment
    namedetails = hit.get("namedetails", {})
    address = hit.get("address", {})
    english_name = (
        namedetails.get("name:en")
        or address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or hit.get("display_name", city).split(",")[0].strip()
    )

    # Build a clean display name: "City, Country"
    country = address.get("country", "")
    clean_display = f"{english_name}, {country}".strip(", ") if country else english_name

    return GeocodeResponse(
        display_name=clean_display,
        lat=float(hit.get("lat", 0)),
        lon=float(hit.get("lon", 0)),
        country_code=address.get("country_code", ""),
        is_country=(
            not address.get("city")
            and not address.get("town")
            and not address.get("village")
            and not address.get("municipality")
            and bool(address.get("country"))
        ),
    )
