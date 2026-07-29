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
