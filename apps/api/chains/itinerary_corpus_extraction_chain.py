"""
Itinerary corpus extraction chain (docs/rag-strategy.md §9, second half of
Phase 2 — "itinerary-corpus-extraction").

Takes the RAW documents fetched by `scrapers/itinerary_corpus.py` (plain
text + light source metadata) and uses a small, cheap Gemini call to turn
each one into a structured `ItineraryCorpusDoc` — the same JSON extraction
pattern already used by `chains/extract_trip_chain.py`, just with a richer
target schema. Documents that don't actually contain a real day-by-day
itinerary (e.g. a listicle that slipped past the scraper's title filter)
are dropped by returning `None` here.

This module also owns embedding + upserting into the new two-named-vector
`itinerary_corpus` Qdrant collection (config vector + content vector, per
the dual-embedding retrieval strategy in the design doc) and computing each
document's `quality_score` from its source type/signal, per the "Source
Quality Scoring" table in rag-strategy.md §9.

Retrieval of this collection (wiring `itinerary_corpus` into the itinerary
generation prompt as few-shot grounding) is the separate, still-pending
`itinerary-corpus-retrieval` roadmap item — this module only ingests.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from core.config import settings
from core.llm_client import track_gemini_usage
from core.prompt_guard import wrap_untrusted

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Target schema
# ---------------------------------------------------------------------------

class ItineraryCorpusDay(BaseModel):
    day_number: int
    theme: str = ""
    places: list[str] = Field(default_factory=list)
    tips: str = ""


class ItineraryCorpusDoc(BaseModel):
    is_itinerary: bool = True
    destination: str | None = None
    country: str | None = None
    duration_days: int | None = None
    pace: str | None = None                # "relaxed" | "moderate" | "packed"
    purpose: str | None = None             # e.g. "cultural", "honeymoon", "adventure"
    budget_tier: str | None = None         # "budget" | "mid-range" | "premium" | "luxury"
    group_type: str | None = None          # "solo" | "couple" | "family" | "friends" | "group"
    published_month: str | None = None
    days: list[ItineraryCorpusDay] = Field(default_factory=list)


_EXTRACTION_SYSTEM_PROMPT = """\
You are a travel-itinerary data extraction assistant. Given raw text scraped \
from a travel blog, Wikivoyage article, Reddit trip report, or YouTube \
caption transcript, determine whether it describes a REAL day-by-day travel \
itinerary (not a generic listicle, review, or unrelated content) and, if so, \
extract it into structured JSON.

RESPONSE FORMAT — respond ONLY with valid JSON, no markdown fences:
{
  "is_itinerary": <true if this text describes an actual day-by-day trip, else false>,
  "destination": "Primary city/region name, or null",
  "country": "Country name, or null",
  "duration_days": <integer total trip length in days, or null>,
  "pace": "one of: relaxed, moderate, packed — your best judgement, or null",
  "purpose": "one of: cultural, adventure, relaxation, honeymoon, family, backpacking, food, nightlife, nature, or null",
  "budget_tier": "one of: budget, mid-range, premium, luxury — inferred from described spending, or null",
  "group_type": "one of: solo, couple, family, friends, group — inferred from narrative voice, or null",
  "published_month": "Month name if the trip dates are mentioned, else null",
  "days": [
    {"day_number": 1, "theme": "short theme e.g. 'Old town exploration'", "places": ["Place A", "Place B"], "tips": "one short practical tip mentioned for this day, or empty string"}
  ]
}

If the text is NOT a real itinerary (e.g. it's a generic "10 best restaurants" \
listicle, a safety FAQ, or unrelated content), respond with "is_itinerary": false \
and leave all other fields null/empty — do not invent details.
Only include days you can actually find evidence for in the text; do not \
fabricate day counts beyond what's described.
"""


async def extract_itinerary_doc(raw_text: str) -> ItineraryCorpusDoc | None:
    """Run one raw scraped document through the extraction LLM call.

    Returns None if the LLM determines this isn't a real itinerary, or if
    extraction fails after retries (fail-closed — we'd rather skip a
    document than pollute the corpus with garbage).
    """
    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    client = google_genai.Client(api_key=settings.gemini_api_key)
    untrusted = wrap_untrusted(raw_text[:6000], label="scraped travel content (blog/wikivoyage/reddit/youtube)")
    prompt = f"Extract itinerary structure from the following text:\n\n{untrusted}"

    for attempt in range(3):
        try:
            def _call_sync():
                return client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=_EXTRACTION_SYSTEM_PROMPT,
                        temperature=0.1,
                        max_output_tokens=1024,
                    ),
                )

            resp = await asyncio.to_thread(_call_sync)
            track_gemini_usage(resp, model="gemini-2.5-flash", purpose="itinerary_corpus_extraction")
            raw = (resp.text or "").strip()
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
            data = json.loads(raw)
            doc = ItineraryCorpusDoc(**data)
            if not doc.is_itinerary or not doc.days:
                return None
            return doc
        except Exception as e:
            logger.warning("Itinerary extraction attempt %d failed: %s", attempt, e)
            if attempt == 2:
                return None
            await asyncio.sleep(1)

    return None


# ---------------------------------------------------------------------------
# Source quality scoring (docs/rag-strategy.md §9 "Source Quality Scoring")
# ---------------------------------------------------------------------------

_AUTHORITATIVE_SOURCES = {"travel_blog", "wikivoyage_itinerary"}


def compute_quality_score(raw_doc: dict[str, Any]) -> float:
    """Map a raw document's source/signal to a quality score in [0, 1],
    per the source-tier table in rag-strategy.md §9."""
    source = raw_doc.get("source", "")

    if source in _AUTHORITATIVE_SOURCES:
        return 0.90

    if source == "reddit_trip_report":
        score = raw_doc.get("reddit_score", 0)
        if score > 500:
            return 0.85
        if score >= 50:
            return 0.65
        return 0.40

    if source == "youtube_captions":
        return 0.55

    return 0.50  # unknown source — conservative middle-of-the-road default


# ---------------------------------------------------------------------------
# Config-text construction + Qdrant upsert
# ---------------------------------------------------------------------------

def _config_text(doc: ItineraryCorpusDoc) -> str:
    """Build the short "config" string embedded for config-similarity
    retrieval, per the design doc's example: '5 day moderate cultural couple
    trip Kyoto Japan November'."""
    parts = [
        f"{doc.duration_days} day" if doc.duration_days else "",
        doc.pace or "",
        doc.purpose or "",
        doc.group_type or "",
        "trip",
        doc.destination or "",
        doc.country or "",
        doc.published_month or "",
    ]
    return " ".join(p for p in parts if p).strip()


def _content_text(doc: ItineraryCorpusDoc) -> str:
    """Build the full day-by-day text embedded for content-similarity
    retrieval."""
    lines = []
    for day in doc.days:
        places = ", ".join(day.places)
        line = f"Day {day.day_number}: {day.theme}. Places: {places}."
        if day.tips:
            line += f" Tip: {day.tips}"
        lines.append(line)
    return "\n".join(lines)


async def ingest_itinerary_corpus() -> int:
    """Full pipeline: fetch raw docs (scrapers/itinerary_corpus.py), extract
    each into a structured ItineraryCorpusDoc, embed (config + content), and
    upsert into the `itinerary_corpus` Qdrant collection.

    Returns the number of documents successfully ingested.
    """
    from scrapers.itinerary_corpus import collect_itinerary_corpus_raw
    from core.qdrant import get_qdrant
    from core.embeddings import embed
    from qdrant_client.models import PointStruct

    raw_docs = await collect_itinerary_corpus_raw()
    if not raw_docs:
        return 0

    extracted: list[tuple[dict[str, Any], ItineraryCorpusDoc]] = []
    for raw_doc in raw_docs:
        try:
            struct_doc = await extract_itinerary_doc(raw_doc["raw_text"])
        except Exception as e:
            logger.warning("Extraction failed for %s: %s", raw_doc.get("source_url"), e)
            continue
        if struct_doc is not None:
            extracted.append((raw_doc, struct_doc))

    if not extracted:
        return 0

    config_texts = [_config_text(doc) for _, doc in extracted]
    content_texts = [_content_text(doc) for _, doc in extracted]
    # Offload the CPU-bound embed() calls to a worker thread so this
    # background ingestion coroutine doesn't block the event loop for
    # concurrent requests (e.g. signup, login) while models run.
    config_vectors = await asyncio.to_thread(embed, config_texts)
    content_vectors = await asyncio.to_thread(embed, content_texts)

    client = get_qdrant()
    points = []
    for (raw_doc, doc), config_vec, content_vec in zip(extracted, config_vectors, content_vectors):
        source_url = raw_doc.get("source_url", "")
        point_id = int(hashlib.md5(source_url.encode()).hexdigest(), 16) % (2**63)
        points.append(PointStruct(
            id=point_id,
            vector={"config": config_vec, "content": content_vec},
            payload={
                "destination": doc.destination,
                "country": doc.country,
                "duration_days": doc.duration_days,
                "pace": doc.pace,
                "purpose": doc.purpose,
                "budget_tier": doc.budget_tier,
                "group_type": doc.group_type,
                "published_month": doc.published_month,
                "source_name": raw_doc.get("source_name"),
                "source_url": source_url,
                "days_json": json.dumps([d.model_dump() for d in doc.days]),
                "quality_score": compute_quality_score(raw_doc),
                "ingested_at": datetime.now(timezone.utc).date().isoformat(),
            },
        ))

    client.upsert(collection_name=settings.qdrant_collection_itinerary_corpus, points=points)
    return len(points)
