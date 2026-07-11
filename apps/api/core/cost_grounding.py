"""
Free-tools-only cost grounding for flights and accommodation.

Budget curation, Part 2.3 of the design memo: rather than a paid flight/hotel
pricing API, this combines two free ingredients:

1. A real-distance-based fare heuristic — haversine distance between origin
   and destination (both already geocoded elsewhere in the app) mapped to a
   banded INR round-trip-economy range. This is deterministic and free, and
   at least grounds the estimate in a real physical quantity (distance)
   instead of the LLM inventing a number with no anchor at all.
2. Community-reported price mentions pulled from the *existing* free RAG
   collections (Reddit/Wikivoyage, already ingested for other purposes) via
   a targeted semantic search — e.g. "flight cost to Bali from India" often
   surfaces real traveller-reported fares/nightly rates in r/travel /
   r/solotravel posts already sitting in Qdrant.

Both are zero-cost, no external paid API calls. The output is a short
grounding hint string injected into the feasibility/expense-estimation
prompts — it does not replace the LLM's own estimate, it constrains it.
"""
from __future__ import annotations
import logging
import math

from models.trip import TripConfig
from services.search import semantic_search

logger = logging.getLogger(__name__)

# (max_km, low_inr, high_inr) round-trip economy, per passenger, India-origin
# assumption. Bands are intentionally wide — this is a sanity-check range,
# not a quote.
_DISTANCE_BANDS: list[tuple[float, int, int]] = [
    (500, 4000, 9000),        # short domestic hop
    (1500, 7000, 15000),      # domestic / near-neighbour international
    (4000, 15000, 30000),     # regional international (SE Asia, Middle East)
    (8000, 28000, 55000),     # long-haul (Europe, East Asia)
    (float("inf"), 45000, 95000),  # ultra-long-haul (Americas, Oceania)
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0  # Earth radius, km
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _distance_band(km: float) -> tuple[int, int]:
    for max_km, low, high in _DISTANCE_BANDS:
        if km <= max_km:
            return low, high
    return _DISTANCE_BANDS[-1][1], _DISTANCE_BANDS[-1][2]


def estimate_flight_cost_range_inr(trip_config: TripConfig) -> tuple[int, int] | None:
    """Real-distance-based free heuristic. Returns (low, high) INR round-trip
    economy per passenger, or None if origin/destination coordinates aren't
    available (e.g. still in country-exploring mode)."""
    origin = trip_config.origin
    dest = trip_config.destination
    if not origin or not dest:
        return None
    if not origin.lat or not origin.lon or not dest.lat or not dest.lon:
        return None

    km = _haversine_km(origin.lat, origin.lon, dest.lat, dest.lon)
    return _distance_band(km)


async def _community_price_snippets(trip_config: TripConfig, query_suffix: str, limit: int = 3) -> list[str]:
    """Best-effort: pull community-reported price mentions from the existing
    free Reddit/Wikivoyage Qdrant collections. Never raises — retrieval
    issues degrade to 'no snippets' rather than blocking cost estimation."""
    dest = trip_config.destination.city if trip_config.destination else ""
    if not dest:
        return []
    try:
        results = await semantic_search(
            query=f"{dest} {query_suffix} price cost INR budget",
            destination=dest,
            limit=limit,
        )
        return [r.text[:280] for r in results]
    except Exception:
        logger.warning("Community price snippet search failed for %s — continuing without it.", dest, exc_info=True)
        return []


async def flight_cost_grounding_hint(trip_config: TripConfig) -> str:
    """Free-tools grounding hint for the flights_inr line item — combines the
    distance heuristic with any community-reported fare mentions found in
    the existing RAG collections."""
    lines: list[str] = []

    band = estimate_flight_cost_range_inr(trip_config)
    if band:
        low, high = band
        origin_city = trip_config.origin.city if trip_config.origin else "origin"
        dest_city = trip_config.destination.city if trip_config.destination else "destination"
        lines.append(
            f"FLIGHT COST GROUNDING (free distance-based heuristic, {origin_city} → {dest_city}): "
            f"round-trip economy fare per passenger should realistically fall in the ₹{low:,}–₹{high:,} range. "
            "Treat this as a sanity-check band, not an exact quote — use your own knowledge to pick a specific "
            "figure within (or, with good reason, slightly outside) this range."
        )

    snippets = await _community_price_snippets(trip_config, "flight airfare")
    if snippets:
        lines.append("COMMUNITY-REPORTED FARE MENTIONS (from real traveller posts, may be dated):")
        for s in snippets:
            lines.append(f"- {s}")

    return "\n".join(lines)


async def accommodation_cost_grounding_hint(trip_config: TripConfig) -> str:
    """Free-tools fallback grounding hint for the accommodation_inr line item
    — used while a Booking.com affiliate/partner pricing feed isn't wired up
    (see todo `booking-accommodation-pricing`). Pulls community-reported
    nightly-rate mentions from the same free RAG collections."""
    snippets = await _community_price_snippets(trip_config, "hotel accommodation nightly rate")
    if not snippets:
        return ""
    lines = ["COMMUNITY-REPORTED ACCOMMODATION RATE MENTIONS (from real traveller posts, may be dated):"]
    for s in snippets:
        lines.append(f"- {s}")
    return "\n".join(lines)
