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

# Some destination names Nominatim only knows as a large administrative
# region/state, not any single city-level place — e.g. "Ladakh" and "Spiti"
# resolve to a union-territory/district-sized boundary whose centroid lands
# far from any populated area, and "Coorg"/"Andaman" resolve similarly (a
# district polygon / a mid-ocean county centroid respectively). Passing that
# centroid + a 5km radius into Overpass then yields ~0 POIs even though the
# geocode itself "succeeds" — live-confirmed 2026-07-23 re-ingesting the
# India tier-2/3 batch (5 destinations came back OSM-zero). Same rationale
# and pattern as scrapers/wikivoyage.py's WIKIVOYAGE_TITLE_OVERRIDES: swap
# in the actual hub city/town travellers use as a base for that region
# before querying Nominatim. Not an exhaustive list; add entries here as
# more region-name-only destinations are found.
GEOCODE_QUERY_OVERRIDES: dict[str, str] = {
    "ladakh": "Leh",
    "spiti": "Kaza",
    "andaman": "Port Blair",
    "coorg": "Madikeri",
}


@lru_cache(maxsize=512)
def _cached_geocode(city: str, lang: str = "en") -> dict | None:
    return None


def _pick_best_hit(hits: list[dict]) -> dict:
    """Nominatim's top hit for a well-known town name is sometimes the
    *district/tehsil-level administrative boundary* it sits in rather than
    the town itself — e.g. "Nainital" and "Jaisalmer" both return their
    encompassing district (`class=boundary, type=administrative`) as hit #1,
    whose centroid is many km from the actual town, before a `class=place`
    city/town/village hit for the real place. Requesting more than one
    result and preferring the first genuine place-level hit (falling back to
    hit #1 if no place-level hit is present, e.g. a country search) fixes the
    resulting Overpass OSM-zero without needing a per-destination override —
    live-confirmed 2026-07-23."""
    for hit in hits:
        if hit.get("class") == "place" and hit.get("type") in ("city", "town", "village"):
            return hit
    return hits[0]


async def geocode_city(city: str, countrycodes: str = "") -> GeocodeResponse:
    global _last_call

    async with _lock:
        now = asyncio.get_event_loop().time()
        wait = (1.0 / settings.nominatim_rate_limit) - (now - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = asyncio.get_event_loop().time()

    query_city = GEOCODE_QUERY_OVERRIDES.get(city.strip().lower(), city)
    params = {
        "q": query_city,
        "format": "json",
        "limit": 5,  # >1 so _pick_best_hit can skip a district-level boundary hit
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

    hit = _pick_best_hit(data)

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
