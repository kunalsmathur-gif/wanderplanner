"""Learning flywheel — the `generated_itineraries` Qdrant collection
(docs/rag-strategy.md roadmap, P1; issue #32).

Every successful live-generated itinerary is stored here, mirroring the
`itinerary_corpus` collection's schema and dual-embedding retrieval strategy
(config vector + content vector) exactly — real generated output becomes
retrievable few-shot grounding for future generations, the same way scraped
traveller itineraries already are (see chains/itinerary_corpus_extraction_chain.py
and services/search.py::retrieve_itinerary_examples for the pattern this
mirrors).

Two independent off switches (`settings.generated_itineraries_store_enabled`
/ `generated_itineraries_retrieval_enabled`) so writing and reading can be
toggled separately — e.g. pausing writes without losing retrieval of what's
already stored, or excluding a bad generation run from grounding future ones
without stopping new writes.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

from core.config import settings
from core.embeddings import embed
from core.qdrant import get_qdrant
from models.trip import TripConfig
from services.search import (
    _CORPUS_MIN_SCORE,
    _corpus_config_query,
    _corpus_duration_days,
    _corpus_group_type,
    _format_corpus_days_brief,
)

logger = logging.getLogger(__name__)


def _content_text_from_raw_days(raw_days: list[dict[str, Any]]) -> str:
    """Build the "content" embedding text from a raw (pre-`_parse_days`)
    itinerary days list — same shape produced by `_gemini_itinerary` /
    `_langchain_itinerary` / `_mock_itinerary` in chains/itinerary_chain.py.
    Mirrors `_content_text()` in chains/itinerary_corpus_extraction_chain.py
    so both collections' content vectors live in the same embedding space."""
    lines = []
    for day in raw_days:
        places = ", ".join(item.get("title", "") for item in day.get("items", []) if item.get("title"))
        lines.append(f"Day {day.get('day_number')}: {day.get('theme', '')}. Places: {places}.")
    return "\n".join(lines)


def _corpus_days_json(raw_days: list[dict[str, Any]]) -> str:
    """Reshape raw itinerary days into the same {day_number, theme, places,
    tips} shape `itinerary_corpus` stores, so both collections are read by
    the same `_format_corpus_days_brief()` formatter at retrieval time."""
    reshaped = []
    for day in raw_days:
        places = [item.get("title", "") for item in day.get("items", []) if item.get("title")]
        reshaped.append({
            "day_number": day.get("day_number", 1),
            "theme": day.get("theme", ""),
            "places": places,
            "tips": "",
        })
    return json.dumps(reshaped)


def compute_generation_id(trip_config: TripConfig, itinerary_raw: dict[str, Any]) -> str | None:
    """Deterministically derive (once, cheaply, no I/O) the Qdrant point id
    a live generation *would* be stored under, so the id can be handed back
    to the client in the same request (`ItineraryResponse.generation_id`,
    issue #34) before the actual embed+upsert happens in the background via
    `store_generated_itinerary`. Returns None for anything that wouldn't be
    stored anyway (disabled, no destination, no days) so the response never
    advertises an id that was never written.

    Deliberately mirrors the eligibility checks in `store_generated_itinerary`
    exactly — call this first, and pass its result straight through to that
    function via `point_id=` so both agree on the same id.
    """
    if not settings.generated_itineraries_store_enabled:
        return None
    dest = trip_config.destination
    if not dest or not dest.city:
        return None
    raw_days = itinerary_raw.get("days") or []
    if not raw_days:
        return None

    config_text = _corpus_config_query(trip_config)
    content_text = _content_text_from_raw_days(raw_days)
    # Unlike itinerary_cache's one-point-per-config-shape key, every
    # generation is stored as its own point (multiple travellers/trips can
    # share the same duration/pace/purpose/destination) — the id only needs
    # to be stable enough to dedupe an exact retry, not to merge distinct
    # generations.
    dedupe_key = f"{config_text}|{content_text}|{datetime.now(UTC).isoformat()}"
    point_id = int(hashlib.md5(dedupe_key.encode()).hexdigest(), 16) % (2**63)
    return str(point_id)


async def store_generated_itinerary(
    trip_config: TripConfig, itinerary_raw: dict[str, Any], point_id: str | None = None
) -> None:
    """Best-effort write of a successfully live-generated itinerary into the
    `generated_itineraries` collection. Never raises — a write failure here
    must never affect the response already being returned to the user, and
    must not meaningfully add to generation latency (call this via
    `asyncio.create_task` at the call site rather than awaiting inline).

    Skips fallback-generated content (mock/cache/error-fallback) — only a
    genuine live LLM result should feed the flywheel, the same rule
    `store_itinerary` (itinerary cache) already applies.

    `point_id` should normally be the value `compute_generation_id()` already
    returned to the caller (so the id handed to the client and the id
    actually written to Qdrant are the same one) — computed fresh here only
    as a fallback for callers that skip that step (e.g. existing tests).
    """
    if not settings.generated_itineraries_store_enabled:
        return
    dest = trip_config.destination
    if not dest or not dest.city:
        return
    raw_days = itinerary_raw.get("days") or []
    if not raw_days:
        return

    try:
        config_text = _corpus_config_query(trip_config)
        content_text = _content_text_from_raw_days(raw_days)
        config_vec, content_vec = await asyncio.to_thread(embed, [config_text, content_text])

        resolved_point_id = int(point_id) if point_id is not None else int(
            hashlib.md5(f"{config_text}|{content_text}|{datetime.now(UTC).isoformat()}".encode()).hexdigest(), 16
        ) % (2**63)

        # A genuine live result that had nothing in our corpus to ground
        # itself in (raw["_context_grounded"] is False) is still real LLM
        # output, but less trustworthy as future few-shot grounding than one
        # that was — reflected as a lower quality_score rather than being
        # excluded outright, consistent with how quality_score already
        # weights itinerary_corpus retrieval (services/search.py).
        quality_score = 0.75 if itinerary_raw.get("_context_grounded") is not False else 0.55

        def _upsert():
            client = get_qdrant()
            client.upsert(
                collection_name=settings.qdrant_collection_generated_itineraries,
                points=[PointStruct(
                    id=resolved_point_id,
                    vector={"config": config_vec, "content": content_vec},
                    payload={
                        "destination": dest.city,
                        "country": dest.country,
                        "duration_days": _corpus_duration_days(trip_config.dates),
                        "pace": trip_config.effective_pace(),
                        "purpose": trip_config.purpose or None,
                        "budget_tier": None,  # not inferred from a raw INR amount today
                        "group_type": _corpus_group_type(trip_config.group),
                        "published_month": None,
                        "source_name": "wanderplanner_generated",
                        "source_url": "",
                        "days_json": _corpus_days_json(raw_days),
                        "quality_score": quality_score,
                        "ingested_at": datetime.now(UTC).date().isoformat(),
                        "generated_at": datetime.now(UTC).isoformat(),
                    },
                )],
            )

        await asyncio.to_thread(_upsert)
    except Exception:
        logger.warning("generated_itineraries write failed (best-effort, ignored)", exc_info=True)


async def retrieve_generated_itinerary_examples(trip_config: TripConfig, limit: int = 2) -> str:
    """Retrieve up to `limit` past live-generated itineraries as additional
    few-shot grounding — same 60/40 config/content weighted-merge +
    quality_score weighting as
    services/search.py::retrieve_itinerary_examples, just pointed at the
    `generated_itineraries` collection instead of the scraped corpus. Kept
    as a separate function (rather than folding into the corpus one) so
    each collection's retrieval can be toggled off independently and a
    failure in one never affects the other."""
    if not settings.generated_itineraries_retrieval_enabled:
        return ""
    if not trip_config.destination or not trip_config.destination.city:
        return ""

    query = _corpus_config_query(trip_config)
    vector = (await asyncio.to_thread(embed, [query]))[0]
    client = get_qdrant()
    city = trip_config.destination.city

    dest_filter = Filter(must=[FieldCondition(key="destination", match=MatchValue(value=city))])

    def _search_named(vector_name: str, use_filter: bool):
        return client.search(
            collection_name=settings.qdrant_collection_generated_itineraries,
            query_vector=(vector_name, vector),
            query_filter=dest_filter if use_filter else None,
            limit=limit * 2,
            with_payload=True,
        )

    try:
        config_hits, content_hits = await asyncio.gather(
            asyncio.to_thread(_search_named, "config", True),
            asyncio.to_thread(_search_named, "content", True),
        )
        # Same free-form-destination-name fallback as
        # retrieve_itinerary_examples: fall back to an unfiltered search +
        # case-insensitive client-side check rather than missing legitimate
        # matches on casing alone.
        if not config_hits and not content_hits:
            config_hits, content_hits = await asyncio.gather(
                asyncio.to_thread(_search_named, "config", False),
                asyncio.to_thread(_search_named, "content", False),
            )
            city_lower = city.strip().lower()
            config_hits = [h for h in config_hits if ((h.payload or {}).get("destination") or "").strip().lower() == city_lower]
            content_hits = [h for h in content_hits if ((h.payload or {}).get("destination") or "").strip().lower() == city_lower]
    except Exception:
        logger.warning("generated_itineraries retrieval failed (best-effort, ignored)", exc_info=True)
        return ""

    merged: dict[int | str, dict] = {}
    for hits, weight in ((config_hits, 0.6), (content_hits, 0.4)):
        for h in hits:
            entry = merged.setdefault(h.id, {"payload": h.payload or {}, "score": 0.0})
            entry["score"] += weight * h.score
    for entry in merged.values():
        quality = float(entry["payload"].get("quality_score", 0.5))
        entry["score"] *= 0.5 + 0.5 * quality

    ranked = sorted(merged.values(), key=lambda e: e["score"], reverse=True)

    examples = []
    for entry in ranked[:limit]:
        if entry["score"] < _CORPUS_MIN_SCORE:
            continue
        p = entry["payload"]
        try:
            days = json.loads(p.get("days_json", "[]"))
        except (TypeError, ValueError):
            continue
        if not days:
            continue
        header_bits = [
            f"{p['duration_days']} days" if p.get("duration_days") else "",
            p.get("pace") or "",
            p.get("purpose") or "",
            p.get("group_type") or "",
        ]
        header = ", ".join(b for b in header_bits if b)
        examples.append(
            f"[Source: a previously generated Wanderplanner itinerary{' — ' + header if header else ''}]\n"
            + _format_corpus_days_brief(days)
        )

    return "\n\n---\n\n".join(examples)
