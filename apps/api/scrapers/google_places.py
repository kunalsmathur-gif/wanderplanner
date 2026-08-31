"""Google Places POI ingester — trial provider (2026-08-26 -> `settings.
google_places_trial_end_date`), see core/config.py's "Google Places POI
trial" block for the full rationale.

Fetches real points of interest for a destination from the Places API (New)
`searchNearby` endpoint and returns them in the exact payload shape
`scrapers/osm.py` produces, so both providers can be upserted into the same
`osm_pois` Qdrant collection interchangeably — no downstream reader
(`services/poi_pinning.py`, `services/search.py`, the itinerary generation
prompt) needs to know or care which provider actually supplied a given POI.

This module deliberately does NOT decide fallback policy or write to Qdrant
itself — `scrapers/poi_provider.py` owns "try Google Places, fall back to
OSM on failure, log which one won" so that decision lives in one place
alongside the eval-tracking row, not duplicated here and in the scheduler.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from core.config import settings
from core.ingestion_metadata import AttractionType, build_ingestion_payload
from services.geocode import geocode_city

logger = logging.getLogger(__name__)

PLACES_API_URL = "https://places.googleapis.com/v1/places:searchNearby"

# Places API (New) "Table A" types (developers.google.com/maps/documentation/
# places/web-service/place-types), grouped the same way `POI_TAG_QUERIES` in
# scrapers/osm.py is: `includedTypes` accepts several types in one call, but
# a broad unrelated mix in a single call measurably hurts result relevance —
# so POIs are fetched in a small number of themed category groups (one call
# each) rather than one give-me-everything call like Overpass supports.
#
# Kept deliberately smaller than OSM's tag list: Places' taxonomy is coarser
# (no separate "historic ruins" vs "archaeological site" vs "castle" the way
# OSM tags do), so several OSM categories collapse into Google's single
# `historical_landmark`/`tourist_attraction` types.
GOOGLE_PLACES_CATEGORY_GROUPS: dict[str, list[str]] = {
    "landmark": [
        "historical_landmark", "monument", "tourist_attraction",
        "place_of_worship", "hindu_temple", "mosque", "church", "synagogue",
    ],
    "museum_art": ["museum", "art_gallery"],
    "nature": ["park", "national_park", "beach", "garden", "zoo", "aquarium"],
    "entertainment": ["tourist_attraction", "amusement_park", "movie_theater", "performing_arts_theater"],
    # Food/drink last on purpose — same "don't let the numerically dominant
    # category crowd out landmarks" reasoning as osm.py's `_prioritize_landmarks`.
    "food_drink": ["restaurant", "cafe", "bar"],
}

# Places -> this repo's shared AttractionType vocabulary (core/ingestion_metadata.py).
# Falls back to "activity" for anything not listed, same default OSM uses.
GOOGLE_PLACES_TYPE_TO_ATTRACTION: dict[str, AttractionType] = {
    "restaurant": "restaurant", "cafe": "restaurant", "bar": "restaurant",
    "museum": "museum", "art_gallery": "museum",
    "park": "nature", "national_park": "nature", "beach": "nature",
    "garden": "nature", "zoo": "nature", "aquarium": "nature",
    "historical_landmark": "landmark", "monument": "landmark",
    "tourist_attraction": "landmark", "place_of_worship": "landmark",
    "hindu_temple": "landmark", "mosque": "landmark", "church": "landmark",
    "synagogue": "landmark",
    "amusement_park": "activity", "movie_theater": "activity",
    "performing_arts_theater": "activity",
}

FIELD_MASK = (
    "places.id,places.displayName,places.location,places.types"
)
# 🔴 Deliberately Pro-SKU fields ONLY (id, displayName, location, types) —
# NOT `places.rating`/`places.userRatingCount`. Google's Places API (New)
# has no "Essentials" tier for Nearby Search; the two real tiers are Pro
# (this field set) and Enterprise (adds rating/userRatingCount, opening
# hours, phone, price level, website). Google bills the WHOLE request at
# whichever tier the highest field present belongs to — so requesting even
# one Enterprise field (e.g. `rating`) tips every call in that request to
# Enterprise pricing, not just that field. See core/config.py's
# "Google Places POI trial" comment block for the actual India per-1000-call
# rates and free-tier caps for both SKUs, and the explicit decision (2026-08-
# 31) to stay on Pro/no-ratings for now.


class GooglePlacesQuotaError(Exception):
    """Raised when Google Places returns something the caller (scrapers/
    poi_provider.py) should treat as "fall back to OSM this run", e.g. no
    API key configured, or the API rejects the key/quota. Kept distinct from
    a bare `httpx.HTTPStatusError` so callers don't need to inspect status
    codes themselves to decide whether a fallback is warranted."""


def _poi_from_place(place: dict[str, Any], destination: str, category: str) -> dict[str, Any] | None:
    name = (place.get("displayName") or {}).get("text", "").strip()
    location = place.get("location") or {}
    lat, lon = location.get("latitude"), location.get("longitude")
    if not name or lat is None or lon is None:
        return None

    types = place.get("types") or []
    primary_type = next((t for t in types if t in GOOGLE_PLACES_TYPE_TO_ATTRACTION), category)
    attraction_type = GOOGLE_PLACES_TYPE_TO_ATTRACTION.get(primary_type, "activity")
    # `rating`/`userRatingCount` are Enterprise-SKU fields and deliberately
    # NOT in FIELD_MASK (see its comment) — Google's response simply omits
    # them, so these always resolve to None on the current Pro-tier field
    # mask. Left as `.get()` lookups (not removed) so re-adding those two
    # fields to FIELD_MASK is the only change needed to bring ratings back.
    rating = place.get("rating")
    rating_count = place.get("userRatingCount")

    text = f"{name} — a {primary_type.replace('_', ' ')} in {destination}."
    if rating is not None and rating_count:
        text += f" Rated {rating}/5 from {rating_count} reviews."

    place_id = place.get("id", "")
    return build_ingestion_payload(
        destination=destination,
        source="google_places",
        text=text,
        source_url=f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else "",
        source_name="Google Places",
        attraction_type=attraction_type,
        extra={
            "name": name,
            "name_local": "",
            "poi_type": primary_type,
            "lat": float(lat),
            "lon": float(lon),
            "prominence": float(rating or 0.0),
            "tags": {},
            "google_place_id": place_id,
            "google_rating": rating,
            "google_rating_count": rating_count,
        },
    )


async def _search_nearby(
    client: httpx.AsyncClient, api_key: str, lat: float, lon: float, radius_m: int, types: list[str],
) -> list[dict[str, Any]]:
    resp = await client.post(
        PLACES_API_URL,
        json={
            "includedTypes": types,
            "maxResultCount": settings.google_places_max_results_per_category,
            "locationRestriction": {
                "circle": {"center": {"latitude": lat, "longitude": lon}, "radius": float(radius_m)},
            },
        },
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        timeout=15,
    )
    if resp.status_code in (401, 403, 429):
        # Bad/blocked key, or quota exhausted — these are exactly the
        # conditions the OSM fallback exists for, not a fatal error.
        raise GooglePlacesQuotaError(f"Places API returned {resp.status_code}: {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json().get("places", [])


async def fetch_google_places_pois(destination: str) -> tuple[list[dict], int]:
    """Fetch POIs for `destination` across all category groups.

    Returns `(pois, call_count)` — the caller (scrapers/poi_provider.py)
    records `call_count` for the trial's cost-tracking table
    (`db_models/poi_provider_usage.py`).

    Raises `GooglePlacesQuotaError` if no key is configured or every call is
    rejected (bad key/quota) — callers should catch this and fall back to
    OSM. Any other exception (network error, unexpected schema) also
    propagates and should be treated the same way by the caller.
    """
    if not settings.google_places_enabled:
        raise GooglePlacesQuotaError("Google Places is disabled (google_places_enabled=False)")
    api_key = settings.google_places_api_key
    if not api_key:
        raise GooglePlacesQuotaError("No Google Places API key configured")

    geo = await geocode_city(destination)
    lat, lon = geo.lat, geo.lon

    pois: list[dict] = []
    seen_names: set[str] = set()
    call_count = 0
    async with httpx.AsyncClient() as client:
        for category, types in GOOGLE_PLACES_CATEGORY_GROUPS.items():
            call_count += 1
            try:
                places = await _search_nearby(
                    client, api_key, lat, lon, settings.osm_poi_radius_m, types,
                )
            except GooglePlacesQuotaError:
                # A blocked/quota-exhausted key fails every subsequent call
                # identically — re-raise immediately rather than burning the
                # remaining category calls on requests certain to also fail.
                raise
            except Exception as e:
                # A single category group failing (network blip, transient
                # 5xx) shouldn't sink the whole destination — skip it and
                # keep going with the categories that do work, same
                # per-item-tolerant spirit as every other scraper in this repo.
                logger.warning("Google Places category %r failed for %r: %s", category, destination, e)
                continue

            for place in places:
                poi = _poi_from_place(place, destination, category)
                if poi is None or poi["name"] in seen_names:
                    continue
                seen_names.add(poi["name"])
                pois.append(poi)

    return pois, call_count


def estimate_cost_usd(call_count: int) -> float:
    """Directional cost estimate for the trial's eval report — see
    `settings.google_places_cost_per_1000_calls_usd` for the pricing source
    and caveats (not accounting-grade; Google's billing console is the
    source of truth)."""
    return round(call_count / 1000 * settings.google_places_cost_per_1000_calls_usd, 6)


def poi_point_id(destination: str, name: str) -> int:
    """Same stable-hash scheme `scrapers/osm.py` uses for `osm_pois` point
    IDs, so a destination re-ingested by the OTHER provider next week
    overwrites the same points rather than accumulating duplicates from both
    providers side by side."""
    point_id = hashlib.md5(f"{destination}::{name}".encode()).hexdigest()
    return int(point_id, 16) % (2**63)
