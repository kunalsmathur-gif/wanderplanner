"""Retrieval for the entry/visa corpus (issue #37).

Kept out of `services/search.py` because the shape is different: that module
returns prompt context blended from several collections, while this returns one
short, attributed note for a single country or nothing at all.

⚠️ **Deliberately framed as background context, never as a determination.**
Wikivoyage is community-maintained and can lag a rule change, so the note is
returned with its source URL and an explicit "verify with the official source"
line. A traveller acting on a stale visa rule misses a flight; the cost of
being wrong here is much higher than for a restaurant recommendation, which is
why this degrades to silence rather than guessing.
"""
from __future__ import annotations

import asyncio
import logging

from qdrant_client.models import FieldCondition, Filter, MatchValue

from core.config import settings
from core.embeddings import embed
from core.qdrant import get_qdrant

logger = logging.getLogger(__name__)

# Below this cosine score the match is not about the asked-for country's entry
# rules in any useful way. Set at the same level as the itinerary corpus's
# floor rather than tuned independently — there is no calibration data yet, and
# inventing a number and calling it calibrated is worse than reusing one.
_MIN_SCORE = 0.30
_MAX_CHUNKS = 3


async def retrieve_visa_note(country: str, query: str = "") -> str:
    """A short, attributed entry-requirements note for `country`, or "" when
    the corpus has nothing usable. Callers treat "" as "say nothing".

    Never raises: a retrieval failure must not take down a wizard turn, so any
    error degrades to "" the same way an empty corpus does.
    """
    if not settings.visa_info_retrieval_enabled or not country.strip():
        return ""

    country = country.strip()
    text = query.strip() or f"visa and entry requirements for {country}"

    try:
        vector = (await asyncio.to_thread(embed, [text]))[0]
        client = get_qdrant()
        hits = await asyncio.to_thread(
            lambda: client.search(
                collection_name=settings.qdrant_collection_visa_info,
                query_vector=vector,
                query_filter=Filter(must=[
                    FieldCondition(key="destination", match=MatchValue(value=country))
                ]),
                limit=_MAX_CHUNKS,
                with_payload=True,
            )
        )
    except Exception as e:
        logger.warning("visa note retrieval failed for %r: %s", country, e)
        return ""

    kept = [h for h in hits if h.score >= _MIN_SCORE]
    if not kept:
        return ""

    lines = [f"Entry requirements for {country} (from Wikivoyage, may be out of date):"]
    lines += [f"- {(h.payload or {}).get('text', '').strip()}" for h in kept]
    source = (kept[0].payload or {}).get("source_url", "")
    if source:
        lines.append(f"Source: {source}")
    lines.append("Always confirm with the destination's official immigration site before booking.")
    return "\n".join(lines)


# ── Cost-estimation grounding ────────────────────────────────────────────────
# The `visa_inr` slot in the itinerary and feasibility prompts was a bare
# "<total visa fees for all passengers>" with nothing behind it, so the number
# came from the model's parametric memory while this corpus — scraped,
# embedded, refreshed on a schedule — went unread by the two chains that
# actually produce it. Bhutan is the case that exposed it: ₹41,000 of "visa"
# for a 5-day trip, which is the international Sustainable Development Fee of
# USD 100/night converted to INR. Indians need no visa for Bhutan and pay an
# SDF of ₹1,200/night, so the estimate was wrong twice over — the wrong rate,
# under the wrong label.
_ENTRY_COST_QUERY = "visa fee cost permit entry requirements for Indian citizens"


async def entry_cost_prompt_hint(country: str) -> str:
    """Grounding for what the plan *says* about entry rules — not for a number.

    ⚠️ `visa_inr` is forced to 0 in both chains, so this block must never be
    framed as "use this to price the visa". It exists because the prose is now
    the only channel for entry-cost information, and prose that names a real
    permit or levy is worth far more than prose hedging in the abstract.

    ⚠️ **Coverage is a fixed list of 73 seed countries and there is no
    real-time fetch.** `_refresh_visa_info` walks `VISA_SEED_COUNTRIES` on a
    schedule; the cold-start path in `services/destination_ingestion.py`
    ingests OSM, Wikivoyage and YouTube for an unseen destination but **not**
    visa rules. So an off-list country (Uzbekistan, Rwanda, Bolivia…) yields ""
    here, permanently, and the model falls back to describing entry
    requirements from its own recollection. That is tolerable only because the
    fee itself is excluded — the failure mode is vaguer prose, not a wrong
    number.

    Best-effort throughout: `retrieve_visa_note` never raises, and an empty
    corpus yields "" rather than blocking a generation.
    """
    note = await retrieve_visa_note(country, query=_ENTRY_COST_QUERY)
    if not note:
        return ""
    return (
        "ENTRY-REQUIREMENT GROUNDING (for what you say about permits/levies in "
        "prose — do NOT turn this into a cost figure; `visa_inr` stays 0):\n"
        f"{note}"
    )
