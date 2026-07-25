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

import asyncio
import logging

from core.config import settings
from core.distance_pricing import flight_band_inr
from models.trip import TripConfig
from services.search import semantic_search

logger = logging.getLogger(__name__)

# Bounded-compute caps for the lexical price sweep below. 400 chunks per
# collection × 3 collections of pure regex is single-digit milliseconds of
# CPU, and only runs on the budget-estimation path (not per itinerary request).
_PRICE_SCAN_MAX_CHUNKS = 400
# Cap on price-bearing snippets handed to the median. Well above `min_samples`
# so the median is stable, low enough to stay bounded on a well-ingested city.
_MAX_PRICE_SAMPLES = 24


def _price_collections() -> list[str]:
    return [
        settings.qdrant_collection_wiki,
        settings.qdrant_collection_reddit,
        settings.qdrant_collection_youtube_comments,
    ]


def _scroll_price_candidates_sync(
    destination: str,
    collections: list[str],
    context_keywords: frozenset[str] | None,
    max_chunks: int = _PRICE_SCAN_MAX_CHUNKS,
) -> list[str]:
    """Every chunk for `destination` that literally contains a price mention.

    This is the fix for the retrieval half of the grounding no-op. Semantic
    search ranks by similarity to a price-flavoured query, which is the wrong
    question: a casual "Choki dani 700 per person" comment is topically about a
    restaurant, not about "cost", so it ranks far below generic prose that
    merely discusses money and never makes the top-`limit` cut. Presence of a
    price is a *lexical* property, so it's tested lexically — a bounded scroll
    plus the same regex the extractor itself uses, no embedding involved.

    Pure CPU + N Qdrant scrolls — call via asyncio.to_thread. Best-effort per
    collection: a missing/unindexed collection is skipped, never fatal.
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from core.price_extraction import _snippet_has_context, has_price_mention
    from core.qdrant import get_qdrant

    client = get_qdrant()
    dest_filter = Filter(
        must=[FieldCondition(key="destination", match=MatchValue(value=destination))]
    )

    snippets: list[str] = []
    for collection in collections:
        try:
            points, _ = client.scroll(
                collection_name=collection,
                scroll_filter=dest_filter,
                limit=max_chunks,
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            logger.debug("Price-candidate scroll failed for %s/%s", destination, collection, exc_info=True)
            continue
        for point in points:
            payload = point.payload or {}
            text = payload.get("text") or payload.get("text_preview") or ""
            if not text or not _snippet_has_context(text, context_keywords):
                continue
            if not has_price_mention(text):
                continue
            # Full chunk text, deliberately NOT excerpted: this path is only
            # ever read by a regex, so the 280-char excerpt that keeps the
            # prompt path's token budget in check would here just discard any
            # *additional* prices later in the same chunk (live-observed —
            # Wikivoyage "Eat"/"Sleep" sections routinely list several in one
            # chunk, and the median needs all of them). Bounded by chunk size
            # × max_chunks, which is already small.
            snippets.append(text)
    return snippets


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
            collections=_price_collections(),
        )
        # Excerpt around the price rather than head-truncating: a chunk whose
        # only amount sits past char 280 used to be handed on with the amount
        # already cut off (see price_focused_excerpt).
        from core.price_extraction import price_focused_excerpt
        return [price_focused_excerpt(r.text) for r in results]
    except Exception:
        logger.warning("Community price snippet search failed for %s — continuing without it.", dest_city, exc_info=True)
        return []


async def community_price_samples(
    dest_city: str,
    query_suffix: str,
    context_keywords: frozenset[str] | None = None,
    limit: int = 5,
) -> list[str]:
    """Snippets to extract a real price figure from — a superset of
    `community_price_snippets`, built for the *extraction* path rather than
    the prompt-hint path.

    Two sources, deliberately in this order:
      1. A lexical sweep for chunks that actually contain a price
         (`_scroll_price_candidates_sync`) — catches the casual, low-topical-
         signal mentions dense retrieval ranks too low to ever return.
      2. The existing semantic search, kept as a complement so a phrasing the
         regex misses can still contribute via topical similarity.

    Kept separate from `community_price_snippets` because that function's
    output goes verbatim into LLM prompts (`flight_cost_grounding_hint`,
    `accommodation_cost_grounding_hint`) where a wider result set would be
    real token bloat; here the snippets are only ever read by a regex.
    """
    if not dest_city:
        return []

    try:
        lexical = await asyncio.to_thread(
            _scroll_price_candidates_sync, dest_city, _price_collections(), context_keywords
        )
    except Exception:
        logger.warning("Lexical price sweep failed for %s — continuing without it.", dest_city, exc_info=True)
        lexical = []

    semantic = await community_price_snippets(dest_city, query_suffix, limit=limit)

    merged: list[str] = []
    seen: set[str] = set()
    for snippet in lexical + semantic:
        key = snippet[:120]
        if key in seen:
            continue
        seen.add(key)
        merged.append(snippet)
        if len(merged) >= _MAX_PRICE_SAMPLES:
            break
    return merged


async def community_median_price_inr(
    dest_city: str,
    query_suffix: str,
    low_bound: float,
    high_bound: float,
    min_samples: int = 2,
    limit: int = 5,
    context_keywords: frozenset[str] | None = None,
    per_day_meal_multiplier: float | None = None,
) -> float | None:
    """Median real per-unit INR price extracted from community snippets for
    `dest_city`, or None if there's too little signal (fewer than
    `min_samples` plausible mentions, or the RAG collections have nothing
    for this destination — currently the common case, see
    core/price_extraction.py's module docstring for why this stays
    regex-based rather than an LLM call).

    `context_keywords` (see core/price_extraction.py) is passed straight
    through — callers pricing a specific line item (e.g. stay vs. food)
    should pass the matching keyword set so an on-topic-looking snippet
    with an off-topic in-bounds amount isn't misread as that line item's
    price.

    `per_day_meal_multiplier` (food only) reconciles per-meal/per-dish
    prices to a per-day budget before the median is taken — see
    core/price_extraction.py::extract_price_mentions_inr."""
    from core.price_extraction import median_price_inr

    snippets = await community_price_samples(
        dest_city, query_suffix, context_keywords=context_keywords, limit=limit
    )
    return median_price_inr(
        snippets, low_bound, high_bound, min_samples, context_keywords, per_day_meal_multiplier
    )


async def community_food_per_day_inr(
    dest_city: str,
    query_suffix: str,
    low_bound: float,
    high_bound: float,
    min_samples: int = 2,
    limit: int = 5,
    context_keywords: frozenset[str] | None = None,
    meals_per_day: float = 3.0,
) -> tuple[float | None, bool]:
    """Food-specific counterpart to `community_median_price_inr`, returning
    `(per_day_inr, directly_observed)` — see
    core/price_extraction.py::food_per_day_estimate_inr. The caller
    (core/budget_estimator.py) uses `directly_observed` to decide whether its
    safety floor still applies."""
    from core.price_extraction import food_per_day_estimate_inr

    snippets = await community_price_samples(
        dest_city, query_suffix, context_keywords=context_keywords, limit=limit
    )
    return food_per_day_estimate_inr(
        snippets, low_bound, high_bound, min_samples, context_keywords, meals_per_day
    )


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
