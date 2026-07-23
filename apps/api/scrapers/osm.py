"""OSM POI ingester — docs §3I.

Fetches real points of interest (name, category, lat/lon, tags) for a
destination from the OpenStreetMap Overpass API and ingests them into the
`osm_pois` Qdrant collection. This gives the itinerary LLM real coordinates
and venue names to ground itineraries in, instead of relying on the model to
invent (and often hallucinate/mis-locate) lat/lon values.

No API key required — Overpass is a free public service, rate-limited by
convention (we keep queries small and destination-scoped).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

import httpx

from core.config import settings
from core.embeddings import embed
from core.qdrant import delete_stale_destination_points, get_qdrant
from services.geocode import geocode_city

logger = logging.getLogger(__name__)

# Overpass's public instance frequently returns transient failures under
# load (429 rate-limit, 504 gateway timeout) — found 2026-07-20 during live
# re-ingestion testing, where a request would fail and succeed seconds later
# on its own. Retrying with backoff here means a scheduled/background
# ingestion job doesn't silently record a destination as having zero POIs
# just because Overpass was briefly busy.
_MAX_FETCH_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 5.0

# OSM tag categories worth surfacing to the itinerary LLM. Each maps to a
# human-readable POI type used in the embedded description text.
#
# Deliberately broad across heritage/culture, nature, sports, arts/science,
# photo-worthy spots, and transport landmarks — not just food/drink — so a
# destination's ingested pool stays well-rounded regardless of any single
# trip's preferences. Per-trip preference weighting (e.g. more parks for a
# toddler, more sports venues for a sports fan) belongs downstream, in
# itinerary-generation retrieval, not here — this pool is shared across
# every trip to the destination.
POI_TAG_QUERIES: dict[str, str] = {
    # Heritage / historic / cultural
    'tourism=attraction': "attraction",
    'tourism=museum': "museum",
    'tourism=gallery': "art gallery",
    'tourism=artwork': "public artwork",
    'tourism=zoo': "zoo",
    'tourism=aquarium': "aquarium",
    'tourism=theme_park': "theme park",
    'historic=monument': "historic monument",
    'historic=castle': "castle",
    'historic=ruins': "historic ruins",
    'historic=archaeological_site': "archaeological site",
    'historic=memorial': "memorial",
    'amenity=place_of_worship': "place of worship",
    # Arts / science / entertainment
    'amenity=theatre': "theatre",
    'amenity=arts_centre': "arts centre",
    'amenity=cinema': "cinema",
    # Sports
    'leisure=stadium': "stadium",
    'leisure=sports_centre': "sports centre",
    # Nature / photo-worthy / outdoors
    'tourism=viewpoint': "viewpoint",
    'leisure=park': "park",
    'leisure=garden': "garden",
    'leisure=nature_reserve': "nature reserve",
    'natural=beach': "beach",
    # Transportation landmarks (useful for orientation, and often
    # destinations in their own right — e.g. King's Cross/Grand Central)
    'railway=station': "train station",
    'aeroway=aerodrome': "airport",
    # Food/drink and shopping — kept last on purpose: see
    # _prioritize_landmarks below, these are numerically dominant in any
    # dense urban core and must not crowd out the categories above.
    'shop=mall': "shopping mall",
    'shop=marketplace': "market",
    'amenity=restaurant': "restaurant",
    'amenity=cafe': "cafe",
    'amenity=bar': "bar",
}


# Once a destination's dense urban core is queried across all tag types in a
# single unioned Overpass call, food/drink establishments vastly outnumber
# landmarks (live-verified: central London within 5km returned 45+ restaurant/
# cafe/bar nodes but as few as 1-2 tourism/historic nodes). A flat Overpass-side
# result cap then fills entirely with food/drink before any landmark node is
# ever seen, starving out exactly the attraction/museum/monument data the
# itinerary LLM and interest-pinning (services/poi_pinning.py) need most.
# Fix: over-fetch from Overpass, then prioritise non-food/drink categories
# client-side before truncating to the final cap.
_RAW_FETCH_MULTIPLIER = 5
_RAW_FETCH_CEILING = 400
_FOOD_DRINK_LABELS = {"restaurant", "cafe", "bar"}


def _build_overpass_query(lat: float, lon: float, radius_m: int) -> str:
    """Build an Overpass QL query for all POI categories around a point."""
    clauses = []
    for tag, _ in POI_TAG_QUERIES.items():
        key, value = tag.split("=", 1)
        clauses.append(f'node["{key}"="{value}"](around:{radius_m},{lat},{lon});')
    body = "\n  ".join(clauses)
    raw_limit = min(settings.osm_poi_max_results * _RAW_FETCH_MULTIPLIER, _RAW_FETCH_CEILING)
    return f"""
[out:json][timeout:25];
(
  {body}
);
out center {raw_limit};
""".strip()


def _poi_type(tags: dict[str, str]) -> str:
    for tag, label in POI_TAG_QUERIES.items():
        key, value = tag.split("=", 1)
        if tags.get(key) == value:
            return label
    return "place of interest"


def _describe_poi(name: str, poi_type: str, destination: str, tags: dict[str, str]) -> str:
    """Build a short natural-language description to embed for semantic search."""
    bits = [f"{name} is a {poi_type} in {destination}."]
    if tags.get("cuisine"):
        bits.append(f"Cuisine: {tags['cuisine'].replace(';', ', ')}.")
    if tags.get("description"):
        bits.append(tags["description"])
    return " ".join(bits)


async def fetch_osm_pois(
    destination: str,
    lat: float | None = None,
    lon: float | None = None,
    radius_m: int | None = None,
) -> list[dict]:
    """Fetch raw POIs for `destination` from Overpass. Geocodes the destination
    first if lat/lon aren't already known. `radius_m` defaults to
    `settings.osm_poi_radius_m`; `ingest_osm_pois` passes the wider
    `osm_poi_radius_expanded_m` as a second pass for thin/category-dominated
    destinations."""
    if lat is None or lon is None:
        geo = await geocode_city(destination)
        lat, lon = geo.lat, geo.lon

    query = _build_overpass_query(lat, lon, radius_m or settings.osm_poi_radius_m)

    # Overpass's usage policy asks for an identifiable User-Agent; some
    # network paths (corporate proxies/CDNs in front of overpass-api.de)
    # also reject POST requests missing an explicit Accept header with a
    # bare 406, so send both defensively.
    headers = {"User-Agent": settings.nominatim_user_agent, "Accept": "*/*"}

    data: dict[str, Any] | None = None
    for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            try:
                resp = await client.post(settings.osm_overpass_url, data={"data": query})
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                if attempt == _MAX_FETCH_ATTEMPTS:
                    logger.warning(
                        "Overpass fetch failed for %r after %d attempts: %s", destination, attempt, e
                    )
                    return []
                await asyncio.sleep(_RETRY_BASE_DELAY_S * attempt)

    pois: list[dict] = []
    seen_names: set[str] = set()
    for element in data.get("elements", []):
        tags: dict[str, str] = element.get("tags", {})
        name = tags.get("name")
        if not name or name in seen_names:
            continue  # skip unnamed nodes — useless for itinerary display
        seen_names.add(name)

        poi_lat = element.get("lat") or (element.get("center") or {}).get("lat")
        poi_lon = element.get("lon") or (element.get("center") or {}).get("lon")
        if poi_lat is None or poi_lon is None:
            continue

        poi_type = _poi_type(tags)
        pois.append({
            "destination": destination,
            "name": name,
            "poi_type": poi_type,
            "lat": float(poi_lat),
            "lon": float(poi_lon),
            "tags": {k: v for k, v in tags.items() if k in ("cuisine", "opening_hours", "website")},
            "text": _describe_poi(name, poi_type, destination, tags),
            "source": "osm",
            "source_url": f"https://www.openstreetmap.org/node/{element.get('id', '')}",
        })

    return _prioritize_landmarks(pois)[: settings.osm_poi_max_results]


def _prioritize_landmarks(pois: list[dict]) -> list[dict]:
    """Round-robin across POI categories so no single tag type can dominate
    the final truncation, with food/drink categories drawn from only after
    every other category is exhausted.

    A plain "food/drink last" stable sort (the original version of this
    function) fixes total food/drink starvation, but doesn't stop a single
    *non*-food/drink category from crowding out the others the same way:
    live-verified 2026-07-20, with only that stable sort in place, a 60-slot
    cap for central Paris came back 51/60 "train station" nodes (Paris's
    metro network is extremely dense) and Tokyo came back 40/60 "place of
    worship" nodes (shrines/temples are extremely common), in both cases
    crowding out museums/attractions/theatres/parks almost entirely — the
    same starvation bug, just relocated to a different category. Round-robin
    selection guarantees every category present gets a turn before any single
    category can fill the remaining slots.
    """
    from collections import defaultdict, deque

    landmark_buckets: dict[str, deque] = defaultdict(deque)
    food_drink_buckets: dict[str, deque] = defaultdict(deque)
    for poi in pois:
        label = poi["poi_type"]
        bucket = food_drink_buckets if label in _FOOD_DRINK_LABELS else landmark_buckets
        bucket[label].append(poi)

    def _round_robin(buckets: dict[str, deque]) -> list[dict]:
        keys = list(buckets.keys())
        ordered: list[dict] = []
        while any(buckets[key] for key in keys):
            for key in keys:
                if buckets[key]:
                    ordered.append(buckets[key].popleft())
        return ordered

    return _round_robin(landmark_buckets) + _round_robin(food_drink_buckets)


# Mirrors eval/data_completeness_scoring.py's MIN_OSM_POIS/MAX_CATEGORY_SHARE
# gate thresholds (not imported directly — that module lives in eval/ and
# pulls in eval-only deps — kept in sync by hand, same as the two other
# nearby "same rationale as X" comments in this file).
_MIN_POIS_BEFORE_RADIUS_EXPANSION = 20
_MAX_CATEGORY_SHARE_BEFORE_EXPANSION = 0.5


def _is_thin_or_dominated(pois: list[dict]) -> bool:
    """True if `pois` would fail the data-completeness gate's OSM checks —
    too few POIs, or a single category crowding out the rest. Small towns/
    "hidden gem" destinations often have this happen at the default 5km
    radius even though a wider radius (still well within a single day-trip
    area) would round out the mix — see `ingest_osm_pois`'s expanded-radius
    retry."""
    if len(pois) < _MIN_POIS_BEFORE_RADIUS_EXPANSION:
        return True
    from collections import Counter

    counts = Counter(p["poi_type"] for p in pois)
    top_share = counts.most_common(1)[0][1] / len(pois)
    return top_share > _MAX_CATEGORY_SHARE_BEFORE_EXPANSION


async def ingest_osm_pois(destination: str) -> int:
    """Fetch and upsert POIs for `destination` into the osm_pois collection.

    Returns the number of POIs ingested. Safe to re-run — point IDs are a
    stable hash of (destination, name), so re-ingestion updates in place
    rather than duplicating.
    """
    pois = await fetch_osm_pois(destination)
    # Thin/single-category-dominated results are common for small towns and
    # "hidden gem" destinations whose few landmark/nature POIs are spread
    # wider than the default 5km while restaurants cluster densely near the
    # centre point — live-confirmed 2026-07-23 (Coorg/Jaisalmer restaurant-
    # dominated, Spiti/Nainital thin). Retry once at a wider radius rather
    # than accepting a food/drink-only pool or an under-20 destination as
    # final; a wider-radius fetch is effectively a superset area so it's
    # never worse, only potentially the same.
    if pois and _is_thin_or_dominated(pois):
        expanded_pois = await fetch_osm_pois(destination, radius_m=settings.osm_poi_radius_expanded_m)
        if expanded_pois and (len(expanded_pois) > len(pois) or not _is_thin_or_dominated(expanded_pois)):
            logger.info(
                "%r: default 5km radius was thin/dominated (%d POIs), expanded to %dm radius (%d POIs)",
                destination, len(pois), settings.osm_poi_radius_expanded_m, len(expanded_pois),
            )
            pois = expanded_pois
    if not pois:
        return 0

    from qdrant_client.models import PointStruct

    texts = [p["text"] for p in pois]
    # Offload the CPU-bound embed() call to a worker thread — this coroutine
    # runs on the scheduler's event loop and must not block other requests.
    vectors = await asyncio.to_thread(embed, texts)

    points = []
    new_ids: set[int] = set()
    for poi, vec in zip(pois, vectors):
        point_id = hashlib.md5(f"{poi['destination']}::{poi['name']}".encode()).hexdigest()
        point_id_int = int(point_id, 16) % (2**63)
        new_ids.add(point_id_int)
        points.append(PointStruct(id=point_id_int, vector=vec, payload=poi))

    client = get_qdrant()
    # Delete-then-upsert per destination — see delete_stale_destination_points'
    # docstring for why this matters (orphaned points from prior
    # category-selection logic otherwise accumulate forever).
    stale_count = delete_stale_destination_points(client, settings.qdrant_collection_osm, destination, new_ids)
    if stale_count:
        logger.info("Deleted %d stale OSM points for %r before re-ingestion", stale_count, destination)
    client.upsert(collection_name=settings.qdrant_collection_osm, points=points)
    return len(points)
