"""RAG-only fallback itinerary builder — Tier 2 (docs §4).

If the LLM call fails and the itinerary cache misses, assemble a *valid*
itinerary directly from retrieved Qdrant content (real OSM POIs) with no
LLM call at all. Lower creativity than an LLM-written plan, but every venue
is a real ingested place — better than hallucinated lat/lon from a model
that's already failing.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta

from core.config import settings
from core.qdrant import get_qdrant
from models.trip import TripConfig

PACE_ITEMS_PER_DAY = {"relaxed": 3, "moderate": 4, "packed": 5}
TIME_SLOTS = [("09:00", "10:30"), ("11:00", "13:00"), ("14:00", "16:00"), ("16:30", "18:30"), ("19:00", "21:00")]
MIN_POIS_FOR_SKELETON = 3  # below this, there's not enough real data to bother


def _fetch_osm_pois_sync(destination: str, limit: int = 40) -> list[dict]:
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    client = get_qdrant()
    dest_filter = Filter(must=[FieldCondition(key="destination", match=MatchValue(value=destination))])
    points, _ = client.scroll(
        collection_name=settings.qdrant_collection_osm,
        scroll_filter=dest_filter,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    return [p.payload or {} for p in points]


def _trip_dates(trip_config: TripConfig) -> tuple[date, int]:
    dates = trip_config.dates if isinstance(trip_config.dates, dict) else {}
    start = dates.get("start_date") or dates.get("start")
    end = dates.get("end_date") or dates.get("end")
    try:
        base = date.fromisoformat(start) if start else date.today() + timedelta(days=30)
    except Exception:
        base = date.today() + timedelta(days=30)
    num_days = 3
    if start and end:
        try:
            num_days = max(1, (date.fromisoformat(end) - base).days)
        except Exception:
            pass
    return base, num_days


async def rag_skeleton_itinerary(trip_config: TripConfig) -> dict | None:
    """Build a minimal valid itinerary purely from ingested OSM POI data.

    Returns None (caller should fall through to Tier 3) if there isn't
    enough ingested POI data for the destination to build a meaningful plan.
    """
    dest = trip_config.destination.city if trip_config.destination else None
    if not dest:
        return None

    try:
        pois = await asyncio.to_thread(_fetch_osm_pois_sync, dest)
    except Exception:
        return None
    if len(pois) < MIN_POIS_FOR_SKELETON:
        return None

    pace = getattr(trip_config, "pace", "moderate") or "moderate"
    items_per_day = PACE_ITEMS_PER_DAY.get(pace, 4)
    base_date, num_days = _trip_dates(trip_config)

    days = []
    poi_idx = 0
    for day_num in range(num_days):
        day_date = (base_date + timedelta(days=day_num)).isoformat()
        items = []
        for slot_idx in range(items_per_day):
            poi = pois[poi_idx % len(pois)]
            poi_idx += 1
            start_t, end_t = TIME_SLOTS[slot_idx % len(TIME_SLOTS)]
            items.append({
                "id": str(uuid.uuid4()),
                "time_start": start_t,
                "time_end": end_t,
                "title": poi.get("name", "Local highlight"),
                "local_name": "",
                "description": poi.get("text", f"Visit {poi.get('name', 'this spot')} in {dest}."),
                "location": {"lat": poi.get("lat", 0.0), "lon": poi.get("lon", 0.0), "address": dest},
                "tags": [poi.get("poi_type", "")] if poi.get("poi_type") else [],
                "booking_url": "",
                "youtube_video_id": "",
                "youtube_search_query": f"{poi.get('name', dest)} {dest} travel guide",
            })
        days.append({
            "day_number": day_num + 1,
            "date": day_date,
            "theme": f"Day {day_num + 1} in {dest}",
            "items": items,
            "transit_warnings": [],
        })

    return {
        "days": days,
        "expense_breakdown": {
            "flights_inr": 0, "visa_inr": 0, "accommodation_inr": 0, "activities_inr": 0,
            "food_inr": 0, "local_transport_inr": 0, "shopping_inr": 0,
            "emergency_buffer_inr": 0, "total_inr": 0,
            "destination_currency_code": "", "total_destination_currency": 0, "num_people": 1,
        },
        "_from_fallback": "rag_skeleton",
    }
