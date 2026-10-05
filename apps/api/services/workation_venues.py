"""Workation-friendly venue signal — docs/plans/india-workation-finder-plan.md §"New
service: services/workation_venues.py".

Infers a "workation-friendly" venue shortlist (cafes, hotels, coworking spaces with a
decent chance of usable wifi) for a destination from OpenStreetMap tags. No new data
source: this reuses the exact Overpass mirror/retry machinery already built for
`scrapers/osm.py`'s POI ingestion (`_overpass_mirrors()`, `_fetch_overpass`-style
retry/backoff, `_is_hard_refusal`) rather than re-implementing Overpass querying, and
resolves the destination's coordinates via `services/geocode.py` the same way
`scrapers/osm.py` does.

Per the plan's "Data/quality notes": wifi/`internet_access` OSM tagging is sparse in
India, so this module degrades gracefully — it returns fewer venues rather than
fabricating wifi coverage, and reports `has_limited_coverage` so the caller (frontend)
can show a disclaimer. Every venue cites its raw OSM tag as provenance, mirroring the
"mentioned in N traveller posts" citation style `services/gems.py` uses for hidden gems.

TODO: cross-reference existing accommodation data (e.g. `core/airbnb_pricing.py`'s
per-city Airbnb listings used for budget estimation) to enrich/validate the hotel
shortlist. Skipped for now — that dataset carries pricing, not wifi/location detail,
so it wouldn't change which venues are wifi-verified; standalone OSM querying is the
primary mechanism per the plan.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx
from pydantic import BaseModel

from core.config import settings
from services.geocode import geocode_city
from scrapers.osm import _is_hard_refusal, _overpass_mirrors

logger = logging.getLogger(__name__)

# Same shape as scrapers/osm.py's retry budget — kept as a separate, smaller
# constant rather than importing osm.py's because workation venue lookups are
# an interactive (user-facing) request, not a background ingestion job, so a
# shorter worst-case wait is preferable to osm.py's more patient 5-attempt
# budget.
_MAX_FETCH_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 2.0
_RETRY_MAX_DELAY_S = 20.0
_RETRY_JITTER_S = 1.5

# Default search radius around the destination's geocoded point. Kept smaller
# than scrapers/osm.py's general POI radius — a traveller looking for a wifi
# cafe to work from cares about what's walkably/short-drive close, not what's
# technically "in" the destination.
_VENUE_RADIUS_M = 4000

# OSM tag -> workation venue category. Deliberately the three categories the
# plan calls out: cafes and hotels (classic WFH/stay spots) plus coworking
# spaces (purpose-built for this use case where they exist).
VENUE_TAG_QUERIES: dict[str, str] = {
    "amenity=cafe": "cafe",
    "tourism=hotel": "hotel",
    "office=coworking": "coworking",
}

# Tags that indicate OSM mappers have actually recorded wifi availability,
# in order of how affirmatively they answer "is there usable wifi here".
# `internet_access=wlan` and `internet_access=yes` are the dedicated tag for
# this; `wifi=yes` is a less common but still-used freeform equivalent.
# `internet_access=no`/`internet_access=terminal` (a shared public terminal,
# not wifi) are deliberately excluded — they are evidence *against* workation
# suitability, not for it.
_WIFI_AFFIRMATIVE_TAGS: list[tuple[str, str]] = [
    ("internet_access", "wlan"),
    ("internet_access", "yes"),
    ("wifi", "yes"),
]

# Below this fraction of venues carrying a verified wifi tag, the result is
# flagged as limited coverage so the frontend can show a disclaimer rather
# than imply the shortlist is exhaustive. Matches the plan's "wifi tagging is
# known to be sparse in India" caveat — this is a signal quality warning, not
# a hard cutoff; venues are still returned.
_LIMITED_COVERAGE_RATIO = 0.3
# Below this many total venues found, coverage is "limited" regardless of
# ratio — a shortlist of 1-2 venues can't make any honest claim either way.
_LIMITED_COVERAGE_MIN_VENUES = 3


class WorkationVenue(BaseModel):
    """A single cafe/hotel/coworking venue with workation (WFH-day) suitability
    signal, cited back to the raw OSM tag it was inferred from."""

    name: str
    category: str  # "cafe" | "hotel" | "coworking"
    lat: float
    lon: float
    has_verified_wifi: bool
    # Raw OSM tag=value this was inferred from, e.g. "internet_access=wlan",
    # or "" when no wifi tag was present at all (has_verified_wifi is then
    # False). Mirrors services/gems.py's "mentioned in N traveller posts"
    # provenance citation — never claim wifi without pointing at the tag.
    wifi_tag_source: str = ""
    address: str = ""


class WorkationVenueResult(BaseModel):
    """Response wrapper so the caller can tell a thin result from a
    comprehensive one and decide whether to show a coverage disclaimer."""

    venues: list[WorkationVenue]
    total_venues_found: int
    venues_with_verified_wifi_count: int
    has_limited_coverage: bool


def _build_venue_query(lat: float, lon: float, radius_m: int) -> str:
    """Overpass QL for cafes/hotels/coworking spaces around a point. Node-only,
    same as scrapers/osm.py's broad pass — coworking spaces and cafes are
    almost always mapped as nodes, and this keeps the query cheap."""
    clauses = []
    for tag in VENUE_TAG_QUERIES:
        key, value = tag.split("=", 1)
        clauses.append(f'node["{key}"="{value}"](around:{radius_m},{lat},{lon});')
    body = "\n  ".join(clauses)
    return f"""
[out:json][timeout:25];
(
  {body}
);
out center;
""".strip()


async def _fetch_overpass_venues(query: str, destination: str) -> list[dict] | None:
    """POST `query` to Overpass, retrying across mirrors on transient
    failure. Reuses scrapers/osm.py's mirror list and hard-refusal detection
    rather than re-implementing them — see that module's `_overpass_mirrors`/
    `_is_hard_refusal` docstrings for why both exist.

    Returns `None` when every attempt fails, distinct from `[]` (the request
    succeeded and genuinely found nothing) — same contract as
    `scrapers.osm._fetch_overpass`.
    """
    headers = {"User-Agent": settings.nominatim_user_agent, "Accept": "*/*"}
    mirrors = _overpass_mirrors()

    for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
        mirror_url = mirrors[(attempt - 1) % len(mirrors)]
        async with httpx.AsyncClient(timeout=60, headers=headers) as client:
            try:
                resp = await client.post(mirror_url, data={"data": query})
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return data.get("elements", [])
            except Exception as e:
                if attempt == _MAX_FETCH_ATTEMPTS:
                    logger.warning(
                        "Overpass venue fetch failed for %r after %d attempts across %d mirrors: %s",
                        destination, attempt, len(mirrors), e,
                    )
                    return None
                if _is_hard_refusal(e):
                    logger.info(
                        "Overpass venue attempt %d/%d for %r hard-refused by %s (%s), rotating mirror",
                        attempt, _MAX_FETCH_ATTEMPTS, destination, mirror_url, e,
                    )
                    continue
                delay = min(_RETRY_BASE_DELAY_S * (2 ** (attempt - 1)), _RETRY_MAX_DELAY_S)
                delay += random.uniform(0, _RETRY_JITTER_S)
                logger.info(
                    "Overpass venue attempt %d/%d for %r failed (%s), retrying in %.1fs",
                    attempt, _MAX_FETCH_ATTEMPTS, destination, e, delay,
                )
                await asyncio.sleep(delay)
    return None


def _venue_category(tags: dict[str, str]) -> str | None:
    for tag, category in VENUE_TAG_QUERIES.items():
        key, value = tag.split("=", 1)
        if tags.get(key) == value:
            return category
    return None


def _wifi_signal(tags: dict[str, str]) -> tuple[bool, str]:
    """Whether `tags` carries an affirmative wifi tag, and the raw tag=value
    citation to show as provenance. Returns (False, "") when no such tag is
    present — callers must not infer wifi absence from this (OSM tagging is
    sparse, not authoritative), only that it wasn't *confirmed*."""
    for key, value in _WIFI_AFFIRMATIVE_TAGS:
        if tags.get(key) == value:
            return True, f"{key}={value}"
    return False, ""


def _address_from_tags(tags: dict[str, str]) -> str:
    """Best-effort address assembled from OSM's `addr:*` tags, which are
    present for some but far from all nodes."""
    parts = [
        tags.get("addr:housenumber", ""),
        tags.get("addr:street", ""),
        tags.get("addr:suburb", ""),
        tags.get("addr:city", ""),
    ]
    return ", ".join(p for p in parts if p).strip(", ")


def _element_to_venue(element: dict) -> WorkationVenue | None:
    tags: dict[str, str] = element.get("tags", {})
    name = (tags.get("name:en") or tags.get("name") or "").strip()
    if not name:
        return None  # unnamed nodes aren't useful to show a traveller

    category = _venue_category(tags)
    if category is None:
        return None

    lat = element.get("lat") or (element.get("center") or {}).get("lat")
    lon = element.get("lon") or (element.get("center") or {}).get("lon")
    if lat is None or lon is None:
        return None

    has_wifi, wifi_source = _wifi_signal(tags)
    return WorkationVenue(
        name=name,
        category=category,
        lat=float(lat),
        lon=float(lon),
        has_verified_wifi=has_wifi,
        wifi_tag_source=wifi_source,
        address=_address_from_tags(tags),
    )


def _rank_venues(venues: list[WorkationVenue]) -> list[WorkationVenue]:
    """Wifi-verified venues first (stable within that) — a traveller looking
    for a WFH spot cares most about the confirmed-wifi ones."""
    return sorted(venues, key=lambda v: not v.has_verified_wifi)


async def find_workation_venues(destination: str, limit: int = 10) -> WorkationVenueResult:
    """Find cafes/hotels/coworking spaces near `destination` and annotate them
    with wifi-availability signal inferred from OSM tags.

    Degrades gracefully rather than fabricating coverage: if Overpass returns
    nothing, or if wifi tagging for this destination is sparse, fewer (or
    zero) venues are returned and `has_limited_coverage` is set so the caller
    can show a disclaimer instead of implying the shortlist is exhaustive.
    """
    geo = await geocode_city(destination)
    query = _build_venue_query(geo.lat, geo.lon, _VENUE_RADIUS_M)
    elements = await _fetch_overpass_venues(query, destination)

    if not elements:
        return WorkationVenueResult(
            venues=[],
            total_venues_found=0,
            venues_with_verified_wifi_count=0,
            has_limited_coverage=True,
        )

    seen_names: set[str] = set()
    venues: list[WorkationVenue] = []
    for element in elements:
        venue = _element_to_venue(element)
        if venue is None or venue.name in seen_names:
            continue
        seen_names.add(venue.name)
        venues.append(venue)

    total_found = len(venues)
    wifi_count = sum(1 for v in venues if v.has_verified_wifi)

    has_limited_coverage = (
        total_found < _LIMITED_COVERAGE_MIN_VENUES
        or (total_found > 0 and wifi_count / total_found < _LIMITED_COVERAGE_RATIO)
    )

    ranked = _rank_venues(venues)[:limit]
    return WorkationVenueResult(
        venues=ranked,
        total_venues_found=total_found,
        venues_with_verified_wifi_count=wifi_count,
        has_limited_coverage=has_limited_coverage,
    )
