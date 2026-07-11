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
from typing import Any

import httpx

from core.config import settings
from core.qdrant import get_qdrant
from core.embeddings import embed
from services.geocode import geocode_city

# OSM tag categories worth surfacing to the itinerary LLM. Each maps to a
# human-readable POI type used in the embedded description text.
POI_TAG_QUERIES: dict[str, str] = {
    'tourism=attraction': "attraction",
    'tourism=museum': "museum",
    'tourism=viewpoint': "viewpoint",
    'tourism=gallery': "art gallery",
    'historic=monument': "historic monument",
    'historic=castle': "castle",
    'amenity=place_of_worship': "place of worship",
    'leisure=park': "park",
    'natural=beach': "beach",
    'amenity=restaurant': "restaurant",
    'amenity=cafe': "cafe",
    'amenity=bar': "bar",
    'shop=mall': "shopping mall",
    'shop=marketplace': "market",
}


def _build_overpass_query(lat: float, lon: float, radius_m: int) -> str:
    """Build an Overpass QL query for all POI categories around a point."""
    clauses = []
    for tag, _ in POI_TAG_QUERIES.items():
        key, value = tag.split("=", 1)
        clauses.append(f'node["{key}"="{value}"](around:{radius_m},{lat},{lon});')
    body = "\n  ".join(clauses)
    return f"""
[out:json][timeout:25];
(
  {body}
);
out center {settings.osm_poi_max_results};
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


async def fetch_osm_pois(destination: str, lat: float | None = None, lon: float | None = None) -> list[dict]:
    """Fetch raw POIs for `destination` from Overpass. Geocodes the destination
    first if lat/lon aren't already known."""
    if lat is None or lon is None:
        geo = await geocode_city(destination)
        lat, lon = geo.lat, geo.lon

    query = _build_overpass_query(lat, lon, settings.osm_poi_radius_m)

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(settings.osm_overpass_url, data={"data": query})
            resp.raise_for_status()
        except Exception:
            return []
        data = resp.json()

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

    return pois[: settings.osm_poi_max_results]


async def ingest_osm_pois(destination: str) -> int:
    """Fetch and upsert POIs for `destination` into the osm_pois collection.

    Returns the number of POIs ingested. Safe to re-run — point IDs are a
    stable hash of (destination, name), so re-ingestion updates in place
    rather than duplicating.
    """
    pois = await fetch_osm_pois(destination)
    if not pois:
        return 0

    from qdrant_client.models import PointStruct

    texts = [p["text"] for p in pois]
    # Offload the CPU-bound embed() call to a worker thread — this coroutine
    # runs on the scheduler's event loop and must not block other requests.
    vectors = await asyncio.to_thread(embed, texts)

    points = []
    for poi, vec in zip(pois, vectors):
        point_id = hashlib.md5(f"{poi['destination']}::{poi['name']}".encode()).hexdigest()
        point_id_int = int(point_id, 16) % (2**63)
        points.append(PointStruct(id=point_id_int, vector=vec, payload=poi))

    client = get_qdrant()
    client.upsert(collection_name=settings.qdrant_collection_osm, points=points)
    return len(points)
