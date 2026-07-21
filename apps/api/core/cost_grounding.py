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

from core.config import settings
from core.distance_pricing import flight_band_inr
from models.trip import TripConfig
from services.search import semantic_search

logger = logging.getLogger(__name__)


def estimate_flight_cost_range_inr(trip_config: TripConfig) -> tuple[int, int] | None:
    """Real-distance-based free heuristic. Returns (low, high) INR round-trip
    economy per passenger, or None if origin/destination coordinates aren't
    available (e.g. still in country-exploring mode)."""
    origin = trip_config.origin
    dest = trip_config.destination
    if not origin or not dest:
        return None
    return flight_band_inr(origin.lat, origin.lon, dest.lat, dest.lon)


async def community_price_snippets(dest_city: str, query_suffix: str, limit: int = 3) -> list[str]:
    """Best-effort: pull community-reported price mentions from the existing
    free Reddit/Wikivoyage/YouTube-comments Qdrant collections. Never raises —
    retrieval issues degrade to 'no snippets' rather than blocking cost
    estimation. Takes a plain city string (rather than a TripConfig) so
    callers that only have a destination name — e.g. core/budget_estimator.py,
    which works on raw partial trip-config dicts — don't need a
    fully-populated TripConfig just to call this.

    Explicitly includes `youtube_comments` alongside the default wiki+reddit
    pair (2026-07-21): reddit is still at 0 points in prod (item 4, blocked
    on approval), but youtube_comments already has real per-visit price
    mentions from vloggers/commenters (e.g. "Choki dani 700 per person") that
    the default wiki+reddit-only search never saw.
    """
    if not dest_city:
        return []
    try:
        results = await semantic_search(
            query=f"{dest_city} {query_suffix} price cost INR budget",
            destination=dest_city,
            limit=limit,
            collections=[
                settings.qdrant_collection_wiki,
                settings.qdrant_collection_reddit,
                settings.qdrant_collection_youtube_comments,
            ],
        )
        return [r.text[:280] for r in results]
    except Exception:
        logger.warning("Community price snippet search failed for %s — continuing without it.", dest_city, exc_info=True)
        return []


async def community_median_price_inr(
    dest_city: str, query_suffix: str, low_bound: float, high_bound: float, min_samples: int = 2, limit: int = 5
) -> float | None:
    """Median real per-unit INR price extracted from community snippets for
    `dest_city`, or None if there's too little signal (fewer than
    `min_samples` plausible mentions, or the RAG collections have nothing
    for this destination — currently the common case, see
    core/price_extraction.py's module docstring for why this stays
    regex-based rather than an LLM call)."""
    from core.price_extraction import median_price_inr

    snippets = await community_price_snippets(dest_city, query_suffix, limit=limit)
    return median_price_inr(snippets, low_bound, high_bound, min_samples)


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

    dest_city = trip_config.destination.city if trip_config.destination else ""
    snippets = await community_price_snippets(dest_city, "flight airfare")
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
    dest_city = trip_config.destination.city if trip_config.destination else ""
    snippets = await community_price_snippets(dest_city, "hotel accommodation nightly rate")
    if not snippets:
        return ""
    lines = ["COMMUNITY-REPORTED ACCOMMODATION RATE MENTIONS (from real traveller posts, may be dated):"]
    for s in snippets:
        lines.append(f"- {s}")
    return "\n".join(lines)
