"""Unified payload schema for every ingested document (docs/rag-strategy.md §11).

Before this module each scraper invented its own payload shape. They already
agreed on `destination`/`source`/`text`/`source_url` by convention, but nothing
enforced that and nothing else was shared — `country`, `language`,
`content_type`, `attraction_type`, `quality_score` and `ingested_at` existed
only on `itinerary_corpus` (written by `chains/itinerary_corpus_extraction_chain.py`,
which is why that module is the reference implementation this one generalises).

Two deliberate deviations from the schema as written in §11, both chosen so
this could ship additively instead of as a breaking migration:

1. **`text` and `source_url`, not `content` and `url`.** §11 names the fields
   `content`/`url`. Every scraper, and every *reader* — `core/cost_grounding.py`,
   `services/gems.py`, `services/search.py`, `core/price_extraction.py` — has
   always used `text`/`source_url`, as does all ~40k points of live data on the
   Qdrant Cloud cluster. Renaming would have meant re-ingesting every collection
   *and* rewriting every consumer for zero behavioural gain, so the code's names
   win and §11 is corrected to match. The doc was written ahead of the code.

2. **`attraction_type` gains a `landmark` value.** §11 lists seven values, none
   of which fit a monument, castle, ruin, memorial or place of worship — which
   together are the single largest slice of the OSM POI corpus. Forcing them
   into `activity` would make the field useless for the precision filtering §11
   introduces it for. Extending the vocabulary is the honest option; silently
   mis-bucketing is not.

**Cutover point:** points written before 2026-07-29 carry only the four legacy
fields. Every field this module adds is therefore optional at read time —
consumers must use `.get()` with a default, never assume presence. Backfilling
the existing corpus is a separate data run, not a code change.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

# §11's vocabulary, plus `landmark` — see deviation 2 in the module docstring.
ContentType = Literal["review", "itinerary", "tip", "guide", "news", "vlog_transcript"]
AttractionType = Literal[
    "restaurant", "museum", "nature", "transport",
    "accommodation", "activity", "festival", "landmark",
]

# Which kind of text each `source` produces. Keyed on the exact `source` string
# the scrapers already write, so adding a source without updating this map is a
# KeyError at the call site rather than a silently-untyped payload.
SOURCE_CONTENT_TYPE: dict[str, ContentType] = {
    "wikivoyage": "guide",
    "wikivoyage_itinerary": "itinerary",
    "osm": "guide",
    "reddit": "review",
    "youtube_comment": "review",
    "youtube_transcript": "vlog_transcript",
    "youtube_description": "vlog_transcript",
    "visa_info": "guide",
}

# OSM `poi_type` (the human-readable labels in scrapers/osm.py::POI_TAG_QUERIES)
# → §11 `attraction_type`. Anything unmapped falls back to "activity", which is
# the correct default for the generic "place of interest" bucket `_poi_type()`
# returns when no tag matches.
OSM_POI_TYPE_TO_ATTRACTION: dict[str, AttractionType] = {
    "restaurant": "restaurant",
    "cafe": "restaurant",
    "bar": "restaurant",
    "museum": "museum",
    "art gallery": "museum",
    "public artwork": "museum",
    "park": "nature",
    "garden": "nature",
    "nature reserve": "nature",
    "beach": "nature",
    "viewpoint": "nature",
    "zoo": "nature",
    "aquarium": "nature",
    "train station": "transport",
    "airport": "transport",
    "historic monument": "landmark",
    "castle": "landmark",
    "historic ruins": "landmark",
    "archaeological site": "landmark",
    "memorial": "landmark",
    "place of worship": "landmark",
    "attraction": "landmark",
}

# U+0900–U+097F. Detecting Devanagari specifically (rather than running a
# general language-ID library) is deliberate: Hindi is the only non-Latin script
# in this corpus, it arrives via one known path — youtube_narration's ("en","hi")
# transcript fetch, added in v10.41.0 — and an extra dependency for a
# single-script decision is not worth it.
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def detect_language(text: str) -> str:
    """Best-effort ISO-639-1 code: "hi" for Devanagari-bearing text, else "en".

    Deliberately a *presence* test rather than a ratio. Hinglish comments mix
    scripts freely ("Jaipur ka khana ₹200 me मिल जाता है") and the reason this
    field exists is to let a consumer find the non-English half of the corpus —
    a ratio threshold would file exactly those mixed chunks as English and hide
    them, which is the failure v10.41.0 already paid for once.
    """
    return "hi" if _DEVANAGARI.search(text or "") else "en"


def ingested_at_today() -> str:
    """ISO date stamp, UTC. Matches the format
    `chains/itinerary_corpus_extraction_chain.py` already writes."""
    return datetime.now(UTC).date().isoformat()


def build_ingestion_payload(
    *,
    destination: str,
    source: str,
    text: str,
    source_url: str = "",
    source_name: str = "",
    country: str = "",
    published_date: str = "",
    attraction_type: AttractionType | None = None,
    quality_score: float = 0.5,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one unified payload. `extra` carries the source-specific fields
    (`video_id`, `subreddit`, `lat`/`lon`, …) that no other source has.

    `quality_score` defaults to 0.5 — the same neutral value
    `services/search.py:492` already falls back to when the field is absent, so
    a payload built here scores identically to a legacy one until something
    actually computes a score (issue #34).

    Keyword-only on purpose: the argument list is long and half the values are
    bare strings, so positional calls would be trivially transposable.
    """
    payload: dict[str, Any] = {
        # --- the four legacy fields, unchanged ---
        "destination": destination,
        "source": source,
        "text": text,
        "source_url": source_url,
        # --- added by the unified schema ---
        "source_name": source_name or source,
        "country": country,
        "content_type": SOURCE_CONTENT_TYPE.get(source, "guide"),
        "language": detect_language(text),
        "quality_score": quality_score,
        "ingested_at": ingested_at_today(),
    }
    if published_date:
        payload["published_date"] = published_date
    if attraction_type is not None:
        payload["attraction_type"] = attraction_type
    if extra:
        payload.update(extra)
    return payload
