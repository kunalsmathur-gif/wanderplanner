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


# On-demand fetch budget. Measured, not guessed: scraping entry rules for an
# off-list country costs 0.6–1.3s (Uzbekistan 1.25s/18 chunks, Rwanda 0.59s/10,
# Bolivia 1.11s/7) and embedding those chunks is 0.04s on a warm process. The
# embedding model's 12s cold load is the only real risk, and by the time this
# runs the RAG retrieval upstream has already warmed it. 4s therefore clears
# the realistic case with headroom while capping the pathological one — and
# this call rides an existing `asyncio.gather`, so it overlaps work that takes
# longer anyway.
_ENTRY_FETCH_TIMEOUT_S = 4.0

# Per-process memo of "does the corpus have this country". Lets the guidance
# block and the expense parser each ask independently without a second lookup
# or an awkward flag threaded through four call frames. Deliberately not
# time-expiring: within one process the answer only changes when *we* ingest,
# and we update it when we do.
_COVERAGE: dict[str, bool] = {}


async def _corpus_has_country(country: str) -> bool:
    """Cheap existence check — a count, not a search: no embedding required."""
    try:
        client = get_qdrant()
        result = await asyncio.to_thread(
            lambda: client.count(
                collection_name=settings.qdrant_collection_visa_info,
                count_filter=Filter(must=[
                    FieldCondition(key="destination", match=MatchValue(value=country))
                ]),
                exact=False,
            )
        )
        return bool(result.count)
    except Exception as e:
        logger.warning("visa coverage check failed for %r: %s", country, e)
        return False


async def ensure_entry_info(country: str) -> bool:
    """True when the corpus can speak to `country`'s entry rules.

    Fetches on demand when it cannot. The scheduler only walks
    `VISA_SEED_COUNTRIES` (73 countries), and the cold-start path in
    `services/destination_ingestion.py` ingests OSM, Wikivoyage and YouTube for
    an unseen destination but **not** visa rules — so without this an off-list
    country would never be covered, no matter how many times it was requested.

    ⚠️ The return value gates whether a visa figure is shown at all. False must
    mean "we do not know", never "it is free" — the caller renders those
    differently, and conflating them is the whole bug this came from.

    Never raises, and never blocks past `_ENTRY_FETCH_TIMEOUT_S`: a slow or
    failed fetch degrades to False, which surfaces as "not available".
    """
    country = (country or "").strip()
    if not settings.visa_info_retrieval_enabled or not country:
        return False
    if country in _COVERAGE:
        return _COVERAGE[country]

    if await _corpus_has_country(country):
        _COVERAGE[country] = True
        return True

    # Not covered — try to fetch it now rather than leave the traveller with
    # nothing until the next scheduled sweep, which may never include them.
    try:
        from scrapers.visa_info import ingest_visa_info

        chunks = await asyncio.wait_for(
            ingest_visa_info(country), timeout=_ENTRY_FETCH_TIMEOUT_S
        )
        covered = bool(chunks)
        logger.info(
            "visa_info on-demand fetch for %r: %d chunks", country, chunks or 0
        )
    except TimeoutError:
        # Deliberately not cached: this says the fetch was slow *this time*,
        # not that the country is unknowable. A later request on a warmer
        # process should get another go.
        logger.warning(
            "visa_info on-demand fetch for %r exceeded %.1fs — skipping",
            country, _ENTRY_FETCH_TIMEOUT_S,
        )
        return False
    except Exception as e:
        logger.warning("visa_info on-demand fetch for %r failed: %s", country, e)
        return False

    _COVERAGE[country] = covered
    return covered


async def entry_cost_grounding(country: str) -> tuple[str, bool]:
    """`(prompt_block, is_covered)` for a destination's entry costs.

    `is_covered` is what decides whether a visa figure may be shown at all;
    the block is what the model prices against when it may. Wikivoyage can lag
    a rule change, and that is accepted — a dated real figure beats both a
    hallucinated one and a blank where a cost exists.
    """
    covered = await ensure_entry_info(country)
    if not covered:
        return "", False

    note = await retrieve_visa_note(country, query=_ENTRY_COST_QUERY)
    if not note:
        # Chunks exist but none clear the relevance floor — we have nothing
        # useful to price against, so treat it as uncovered rather than let
        # the model fill the silence.
        return "", False

    return (
        "ENTRY-COST GROUNDING — prefer this over your own recollection when "
        "setting `visa_inr`. It may be out of date; say so rather than "
        "dropping the figure:\n"
        f"{note}",
        True,
    )
