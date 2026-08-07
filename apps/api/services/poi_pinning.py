"""Candidate-POI verification for refinement hard-constraints (GTM §2,
the "Harry Potter test").

Takes the place names proposed by chains/interest_expansion_chain.py and
confirms each against data we already ingest, in priority order:

1. `osm_pois` — fuzzy name match against OSM-verified POIs for the
   destination. Survivors get the POI's real lat/lon (verified_by="osm").
2. `wiki` — substring presence in a Wikivoyage/wiki chunk for the
   destination, *and* that same chunk also mentions the named interest
   (e.g. "Harry Potter"). Confirms both that the place exists and that the
   guide itself ties it to the user's stated reason for wanting it — mere
   existence isn't enough (a market being real doesn't mean it's a Harry
   Potter place; see the recurring "Borough Market" false positive).
   Verified_by="wiki" pins carry no coordinates; the generation prompt
   handles that case explicitly.

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
from core.keyword_match import has_keyword
from core.qdrant import get_qdrant
from models.trip import MAX_PINNED_POIS, PinnedPOI

# Same bounded destination-scroll helper gems.py uses — shared on purpose so
# both verification paths stay within identical compute caps.
from services.gems import _MAX_CHUNKS, _MAX_POIS, _scroll_destination

# `_normalize` is re-exported under its original name because
# chains/itinerary_chain.py and eval/refinement_scoring.py import it from here.
from services.name_matching import normalize_name as _normalize

logger = logging.getLogger(__name__)

_FUZZY_THRESHOLD = 0.80

# Words too generic to count as a thematic signal on their own (would make
# almost any wiki chunk "co-occur" with almost any interest).
_INTEREST_STOPWORDS = {
    "and", "the", "a", "an", "of", "in", "for", "to", "with", "on", "at",
    "or", "is", "are", "my", "i", "im", "some", "any", "all",
}


def _interest_keywords(source_interest: str) -> set[str]:
    """Split a free-text named interest ("Harry Potter", "zen gardens and
    temples") into the words worth checking for thematic co-occurrence.
    Empty when the interest is blank or entirely stopwords — callers treat
    that as "nothing to check relevance against"."""
    norm = _normalize(source_interest)
    return {w for w in norm.split() if w and w not in _INTEREST_STOPWORDS and len(w) > 2}


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


def _best_osm_match(cand_norm: str, poi_index: list[tuple[str, dict]]) -> dict | None:
    """Strongest match wins, not the first fuzzy hit in scroll order: exact,
    then containment, then fuzzy. Live 2026-07-13: candidate \"Ginkaku-ji\"
    fuzzy-matched \"Kinkaku-ji\" (ratio 0.89) which happened to sit earlier in
    the index than the exact \"Ginkaku-ji\" entry, silently pinning the wrong
    temple and double-counting its sibling."""
    for norm, poi in poi_index:
        if cand_norm == norm:
            return poi
    for norm, poi in poi_index:
        if (len(cand_norm) >= 6 and cand_norm in norm) or (len(norm) >= 6 and norm in cand_norm):
            return poi
    for norm, poi in poi_index:
        if SequenceMatcher(None, cand_norm, norm).ratio() >= _FUZZY_THRESHOLD:
            return poi
    return None


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

    # Wiki text is only scrolled if at least one candidate misses OSM. Kept as
    # a list of per-chunk texts (not one joined blob) so a candidate match can
    # be checked for thematic co-occurrence with the source interest within
    # the *same* chunk, not "mentioned somewhere in this city's entire guide".
    wiki_chunk_texts: list[str] | None = None

    def _wiki_chunks() -> list[str]:
        nonlocal wiki_chunk_texts
        if wiki_chunk_texts is None:
            chunks = _scroll_destination(
                client, settings.qdrant_collection_wiki, destination, _MAX_CHUNKS
            )
            wiki_chunk_texts = [
                _normalize(c.get("text") or c.get("text_preview") or "") for c in chunks
            ]
        return wiki_chunk_texts

    interest_keywords = _interest_keywords(source_interest)

    pins: list[PinnedPOI] = []
    dropped: list[str] = []
    seen_norms: set[str] = set()
    for candidate in candidates:
        cand_norm = _normalize(candidate)
        if not cand_norm or cand_norm in seen_norms:
            continue
        seen_norms.add(cand_norm)

        osm_hit = _best_osm_match(cand_norm, poi_index)
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

        if len(cand_norm) >= 6:
            matched_chunks = [chunk for chunk in _wiki_chunks() if cand_norm in chunk]
            if matched_chunks and (
                not interest_keywords
                # Word-boundary: _interest_keywords yields any word over two
                # chars, so "art" matched "apartment" and "zen" matched
                # "frozen", falsely confirming a wiki-verified pin.
                or any(has_keyword(chunk, interest_keywords) for chunk in matched_chunks)
            ):
                pins.append(PinnedPOI(
                    name=candidate,
                    source_interest=source_interest,
                    verified_by="wiki",
                ))
                continue
            # Mentioned in the guide but not thematically tied to the user's
            # named interest anywhere it's mentioned (the recurring "Borough
            # Market" false positive for a Harry Potter refinement — real
            # place, just not why the user asked for it). Existence alone
            # isn't enough to force a "must include, matches your interest"
            # hard constraint; treat as unverified rather than invent a link.

        dropped.append(candidate)

    return pins, dropped


# Below this many ingested OSM POIs for a destination, we treat the corpus
# as too thin to conclude anything about a specific unmatched title — a
# destination this sparsely mapped legitimately has real places our OSM
# ingest never captured, so an unmatched item there is "unverified" (safe
# LLM-fallback, keep + tag), not "fabricated" (drop). At/above this count the
# destination is well-enough covered that an item still failing both OSM and
# wiki checks is far more likely to be something the model invented outright
# than a real place we simply missed — e.g. a well-mapped city like Paris or
# Bali with hundreds of ingested POIs vs. a thinly-covered small town with a
# handful. Chosen well below _MAX_POIS (300) so "well covered" doesn't
# require near-total corpus saturation to qualify.
_SPARSE_CORPUS_THRESHOLD = 15


# Words that mark a title as pure trip logistics — a meal, transfer, hotel
# check-in/out, packing, or shopping errand — rather than a claim that a
# specific named venue exists. These were never meant to correspond to an
# OSM POI (there is no place literally named "Hotel Check-out"), so checking
# them against the corpus at all was the bug: on a well-populated corpus
# (corpus_populated=True) every one of these failed to match anything and
# got dropped as "fabricated", which is how a whole itinerary — "Airport
# Transfer & Hotel Check-in", "Leisurely Breakfast & Packing", "Last-minute
# Souvenir Shopping", ... — ended up gutted for a single well-covered
# destination (Bali) instead of the rare one-off fabricated landmark this
# check was built for. Exempted outright rather than verified.
_LOGISTICS_TITLE_KEYWORDS = [
    "check-in", "check in", "checkin", "check-out", "check out", "checkout",
    "transfer", "transit", "departure", "arrival",
    "breakfast", "lunch", "dinner", "meal",
    "packing", "pack", "unpack",
    "shopping", "souvenir",
    "relax", "unwind", "free time", "leisure time", "rest", "downtime",
]


def _is_logistics_title(title: str) -> bool:
    """True when a title is pure trip logistics (meal/transfer/check-in-out/
    packing/shopping/downtime) rather than a claim that a specific named
    venue exists — see _LOGISTICS_TITLE_KEYWORDS for why these are exempted
    from verification entirely instead of being checked against the corpus."""
    return has_keyword(title, _LOGISTICS_TITLE_KEYWORDS)


# Splits a compound title ("Kelingking Beach & T-Rex Cliff", "Kecak Fire
# Dance at Uluwatu", "Transfer to Sanur Port") into its candidate venue
# phrases. Itinerary items are routinely titled as an activity plus a place
# ("... at/in/near/to Place") or two places joined by "&"/"and" — verifying
# the FULL title as one string against corpus POI names, as the original
# version of this check did, means a real, well-ingested place like
# "Uluwatu" or "Kelingking Beach" never gets credit because the literal POI
# name is only ever a fragment of the generated title, not the whole thing.
_TITLE_SPLIT_PATTERN = re.compile(
    r"\s*(?:&|,|\band\b|\bat\b|\bin\b|\bnear\b|\bto\b|\bfrom\b|\bon\b|\bvia\b)\s*",
    re.IGNORECASE,
)


def _title_components(title: str) -> list[str]:
    """Full title first (preserves any existing exact/fuzzy match), then its
    candidate venue-phrase fragments split on common joiners/prepositions,
    each checked independently against the corpus."""
    parts = [title, *_TITLE_SPLIT_PATTERN.split(title)]
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        part = part.strip(" -\u2013\u2014")
        if len(part) < 3 or part.lower() in seen:
            continue
        seen.add(part.lower())
        out.append(part)
    return out


def verify_item_titles_sync(titles: list[str], destination: str) -> tuple[set[str], bool]:
    """Cheaper sibling of verify_candidates_sync for per-item itinerary
    provenance tagging (not refinement pins): just "does this title
    correspond to something in our ingested OSM POIs or get mentioned in a
    wiki chunk for this destination", no source-interest co-occurrence check
    (there is no single "reason" for an item the way there is for a
    refinement candidate). Returns (verified titles, corpus_populated) —
    callers diff titles against the verified set to find the rest, and use
    corpus_populated to decide whether an unmatched title is "fabricated"
    (well-covered destination, still no match — drop it) or merely
    "unverified" (thin destination corpus — keep it, tag it, LLM fallback is
    the safe call). Same bounded scrolls/matcher as verify_candidates_sync,
    so same zero-LLM, zero-external-API cost profile.
    """
    if not titles or not destination:
        return set(), False

    client = get_qdrant()
    pois = _scroll_destination(client, settings.qdrant_collection_osm, destination, _MAX_POIS)
    poi_index = [
        (_normalize(p.get("name") or ""), p) for p in pois if (p.get("name") or "").strip()
    ]
    corpus_populated = len(poi_index) >= _SPARSE_CORPUS_THRESHOLD

    wiki_chunk_texts: list[str] | None = None

    def _wiki_chunks() -> list[str]:
        nonlocal wiki_chunk_texts
        if wiki_chunk_texts is None:
            chunks = _scroll_destination(
                client, settings.qdrant_collection_wiki, destination, _MAX_CHUNKS
            )
            wiki_chunk_texts = [
                _normalize(c.get("text") or c.get("text_preview") or "") for c in chunks
            ]
        return wiki_chunk_texts

    verified: set[str] = set()
    for title in titles:
        if _is_logistics_title(title):
            # Not a venue claim at all — see _is_logistics_title. Verified
            # outright so it's never flagged/dropped by the caller.
            verified.add(title)
            continue
        # Check the full title, then each split-out venue-phrase fragment
        # (see _title_components) — a compound title only needs ONE real
        # component to be considered grounded, since the rest may be an
        # ordinary activity word ("Fast Boat to Sanur" is verified by
        # "Sanur" alone).
        for component in _title_components(title):
            norm = _normalize(component)
            if not norm:
                continue
            if _best_osm_match(norm, poi_index) is not None:
                verified.add(title)
                break
            if len(norm) >= 6 and any(norm in chunk for chunk in _wiki_chunks()):
                verified.add(title)
                break
    return verified, corpus_populated


async def verify_item_titles(titles: list[str], destination: str) -> tuple[set[str], bool]:
    """Async wrapper for verify_item_titles_sync — Qdrant scrolls + string
    matching off the event loop, same failure discipline as
    verify_candidates: a lookup failure must never crash generation, it just
    means nothing gets marked verified this time, and the corpus is reported
    as not-populated so callers fail safe (keep + tag rather than drop) when
    the lookup itself couldn't run."""
    try:
        return await asyncio.to_thread(verify_item_titles_sync, titles, destination)
    except Exception:
        logger.warning("Item-title verification failed; leaving all unverified", exc_info=True)
        return set(), False


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
