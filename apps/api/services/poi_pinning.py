"""Candidate-POI verification for refinement hard-constraints (GTM §2,
the "Harry Potter test").

Takes the place names proposed by chains/interest_expansion_chain.py and
confirms each against data we already ingest, in priority order:

1. `osm_pois` — fuzzy name match against OSM-verified POIs for the
   destination. Survivors get the POI's real lat/lon (verified_by="osm").
2. `wiki` — substring presence in Wikivoyage/wiki chunk text for the
   destination. Confirms the place exists (verified_by="wiki") but carries
   no coordinates; the generation prompt handles that case explicitly.

Anything unverified is dropped — a candidate the LLM invented can never be
pinned. This mirrors the "if OSM doesn't know it, we don't rank it" rule in
services/gems.py.

Scale/latency/cost: zero LLM calls, zero external APIs. Two bounded Qdrant
scrolls (same caps as gems.py) + pure-CPU string matching over ≤10
candidates, run via asyncio.to_thread so the event loop never blocks.
"""
from __future__ import annotations

import asyncio
import logging
import re
from difflib import SequenceMatcher

from core.config import settings
from core.qdrant import get_qdrant
from models.trip import MAX_PINNED_POIS, PinnedPOI
# Same bounded destination-scroll helper gems.py uses — shared on purpose so
# both verification paths stay within identical compute caps.
from services.gems import _scroll_destination, _MAX_POIS, _MAX_CHUNKS

logger = logging.getLogger(__name__)

_FUZZY_THRESHOLD = 0.80


def _normalize(name: str) -> str:
    """Lowercase, strip punctuation/diacritic-ish noise, collapse whitespace."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def _names_match(candidate_norm: str, poi_norm: str) -> bool:
    """True when the normalized names refer to the same place: exact,
    containment (\"warner bros studio tour\" ⊂ \"warner bros studio tour london\"),
    or high SequenceMatcher similarity."""
    if not candidate_norm or not poi_norm:
        return False
    if candidate_norm == poi_norm:
        return True
    if len(candidate_norm) >= 6 and candidate_norm in poi_norm:
        return True
    if len(poi_norm) >= 6 and poi_norm in candidate_norm:
        return True
    return SequenceMatcher(None, candidate_norm, poi_norm).ratio() >= _FUZZY_THRESHOLD


def verify_candidates_sync(
    candidates: list[str], destination: str, source_interest: str = ""
) -> tuple[list[PinnedPOI], list[str]]:
    """Verify candidate names against osm_pois then wiki chunks.

    Returns (verified pins, dropped candidate names). Pure CPU + two bounded
    Qdrant scrolls — call via asyncio.to_thread.
    """
    if not candidates or not destination:
        return [], list(candidates)

    client = get_qdrant()
    pois = _scroll_destination(client, settings.qdrant_collection_osm, destination, _MAX_POIS)
    poi_index = [
        (_normalize(p.get("name") or ""), p) for p in pois if (p.get("name") or "").strip()
    ]

    # Wiki text is only scrolled if at least one candidate misses OSM.
    wiki_blob: str | None = None

    def _wiki_text() -> str:
        nonlocal wiki_blob
        if wiki_blob is None:
            chunks = _scroll_destination(
                client, settings.qdrant_collection_wiki, destination, _MAX_CHUNKS
            )
            wiki_blob = " ".join(
                _normalize(c.get("text") or c.get("text_preview") or "") for c in chunks
            )
        return wiki_blob

    pins: list[PinnedPOI] = []
    dropped: list[str] = []
    seen_norms: set[str] = set()
    for candidate in candidates:
        cand_norm = _normalize(candidate)
        if not cand_norm or cand_norm in seen_norms:
            continue
        seen_norms.add(cand_norm)

        osm_hit = next((p for norm, p in poi_index if _names_match(cand_norm, norm)), None)
        if osm_hit is not None:
            pins.append(PinnedPOI(
                name=osm_hit.get("name") or candidate,
                lat=osm_hit.get("lat", 0.0),
                lon=osm_hit.get("lon", 0.0),
                poi_type=osm_hit.get("poi_type", ""),
                source_interest=source_interest,
                verified_by="osm",
            ))
            continue

        if len(cand_norm) >= 6 and cand_norm in _wiki_text():
            pins.append(PinnedPOI(
                name=candidate,
                source_interest=source_interest,
                verified_by="wiki",
            ))
            continue

        dropped.append(candidate)

    return pins, dropped


async def verify_candidates(
    candidates: list[str], destination: str, source_interest: str = ""
) -> tuple[list[PinnedPOI], list[str]]:
    """Async wrapper — Qdrant scrolls + string matching off the event loop."""
    try:
        return await asyncio.to_thread(
            verify_candidates_sync, candidates, destination, source_interest
        )
    except Exception:
        logger.warning("POI verification failed; dropping all candidates", exc_info=True)
        return [], list(candidates)


def merge_pins(existing: list[PinnedPOI], new: list[PinnedPOI]) -> list[PinnedPOI]:
    """Existing pins first (user commitments are stable), new ones appended,
    deduped by normalized name, capped at MAX_PINNED_POIS."""
    merged: list[PinnedPOI] = []
    seen: set[str] = set()
    for pin in [*existing, *new]:
        norm = _normalize(pin.name)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        merged.append(pin)
    return merged[:MAX_PINNED_POIS]
