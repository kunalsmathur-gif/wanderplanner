"""Semantic search service — queries Qdrant collections."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from qdrant_client.models import Filter, FieldCondition, MatchValue

from core.config import settings
from core.qdrant import get_qdrant
from core.embeddings import embed
from models.common import SearchResult
from models.trip import TripConfig


# ---------------------------------------------------------------------------
# Primitive: single-query Qdrant search
# ---------------------------------------------------------------------------

async def semantic_search(
    query: str, destination: str, limit: int = 10
) -> list[SearchResult]:
    vector = embed([query])[0]
    client = get_qdrant()

    dest_filter = Filter(
        must=[FieldCondition(key="destination", match=MatchValue(value=destination))]
    )

    results = []
    for collection in [settings.qdrant_collection_wiki, settings.qdrant_collection_reddit]:
        hits = client.search(
            collection_name=collection,
            query_vector=vector,
            query_filter=dest_filter,
            limit=limit // 2,
        )
        for hit in hits:
            p = hit.payload or {}
            results.append(SearchResult(
                text=p.get("text", p.get("text_preview", "")),
                source=p.get("source", collection),
                source_url=p.get("source_url", p.get("post_url", "")),
                score=hit.score,
                destination=p.get("destination", destination),
                published_date=p.get("published_date"),
            ))

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]


# ---------------------------------------------------------------------------
# RRF merge
# ---------------------------------------------------------------------------

def _rrf_merge(result_lists: list[list[SearchResult]], k: int = 60) -> list[SearchResult]:
    """
    Reciprocal Rank Fusion across multiple ranked result lists.

    RRF score for a document d = Σ  1 / (k + rank_i(d))
    where rank_i is 1-based position in the i-th result list.

    Keeps the SearchResult with the highest raw cosine score for each unique
    chunk (deduped by the first 120 chars of text).
    """
    rrf_scores: dict[str, float] = {}
    best: dict[str, SearchResult] = {}

    for result_list in result_lists:
        for rank, result in enumerate(result_list, start=1):
            key = result.text[:120]
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in best or result.score > best[key].score:
                best[key] = result

    sorted_keys = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)
    return [best[key].model_copy(update={"score": rrf_scores[key]}) for key in sorted_keys]


# ---------------------------------------------------------------------------
# Time-decay scoring
# ---------------------------------------------------------------------------

def _time_decay_score(base_score: float, published_date: str | None) -> float:
    """
    Apply exponential decay based on content age.
    Half-life: 18 months (548 days). Floor: 40% of base score.
    Unknown dates get a moderate 15% penalty.
    """
    if not published_date:
        return base_score * 0.85

    try:
        pub = datetime.fromisoformat(published_date).replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - pub).days
        decay = 0.5 ** (age_days / 548)
        return base_score * (0.4 + 0.6 * decay)
    except Exception:
        return base_score * 0.85


# ---------------------------------------------------------------------------
# High-level retrieval
# ---------------------------------------------------------------------------

async def retrieve_context(trip_config: TripConfig) -> list[dict]:
    """
    Retrieve the top-20 context chunks for itinerary generation.

    Runs three query variants in parallel and merges with Reciprocal Rank
    Fusion so both specific terms ("anime cafes") and vibe queries
    ("relaxed cultural experience") are well-covered.
    """
    dest = trip_config.destination.city if trip_config.destination else "general"
    personas = " ".join(trip_config.personas).replace("_", " ") if trip_config.personas else ""
    purpose = getattr(trip_config, "purpose", "") or ""
    pace = getattr(trip_config, "pace", "") or ""

    queries = [
        # Query 1 — config-oriented: persona + core nouns
        f"{dest} travel {personas} highlights activities food",
        # Query 2 — purpose/vibe: what kind of trip
        f"things to do in {dest} {purpose} {pace} trip hidden gems local tips",
        # Query 3 — practical: logistics, advice, warnings
        f"{dest} best restaurants sightseeing transport safety advice",
    ]

    result_lists = await asyncio.gather(
        *[semantic_search(q, dest, limit=15) for q in queries]
    )

    merged = _rrf_merge(list(result_lists))[:20]

    return [
        {
            "text": r.text,
            "source": r.source,
            "url": r.source_url,
            "score": r.score,
            "published_date": r.published_date,
        }
        for r in merged
    ]


# ---------------------------------------------------------------------------
# Context compression
# ---------------------------------------------------------------------------

def summarise_context(docs: list[dict], max_chars: int = 2400) -> str:
    """
    Compress retrieved chunks to a fixed token budget before LLM injection.

    Steps:
    1. Apply time-decay to scores (penalises stale content)
    2. Drop chunks with decayed score < 0.35
    3. Deduplicate by Jaccard word overlap (>0.60 → keep highest-scored)
    4. Sort by decayed score DESC
    5. Truncate at max_chars (≈ 600 tokens at ~4 chars/token)

    Falls back to all docs (no filtering) if Qdrant is empty or all scores
    are below threshold.
    """
    MIN_SCORE = 0.35
    JACCARD_THRESHOLD = 0.6

    # Step 1 — apply time-decay
    decayed = [
        {**d, "score": _time_decay_score(d.get("score", 1.0), d.get("published_date"))}
        for d in docs
    ]

    # Step 2 — score filter
    filtered = [d for d in decayed if d["score"] >= MIN_SCORE] or decayed

    # Step 3 — Jaccard deduplication
    def _words(text: str) -> set[str]:
        return set(text.lower().split())

    deduped: list[dict] = []
    for candidate in filtered:
        cand_words = _words(candidate["text"])
        duplicate_of: int | None = None
        for idx, existing in enumerate(deduped):
            exist_words = _words(existing["text"])
            union = cand_words | exist_words
            if union and len(cand_words & exist_words) / len(union) > JACCARD_THRESHOLD:
                duplicate_of = idx
                break

        if duplicate_of is not None:
            if candidate["score"] > deduped[duplicate_of]["score"]:
                deduped[duplicate_of] = candidate
        else:
            deduped.append(candidate)

    # Step 4 — sort by decayed score
    deduped.sort(key=lambda d: d["score"], reverse=True)

    # Step 5 — truncate to budget
    parts: list[str] = []
    total = 0
    for doc in deduped:
        text = doc["text"]
        if total + len(text) > max_chars:
            remaining = max_chars - total
            if remaining > 100:
                parts.append(text[:remaining].rsplit(" ", 1)[0])
            break
        parts.append(text)
        total += len(text)

    return "\n\n".join(parts)
