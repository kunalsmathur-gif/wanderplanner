"""Semantic search service — queries Qdrant collections."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from qdrant_client.models import Filter, FieldCondition, MatchValue

from core.config import settings
from core.qdrant import get_qdrant
from core.embeddings import embed, rerank_scores
from services.hyde import generate_hypothetical_passage
from models.common import SearchResult
from models.trip import TripConfig

# Persona/occasion -> extra query keywords used to bias retrieval toward
# relevant content in the existing free wiki/reddit collections (design memo
# Part 1.3 "Mechanism A"). Hand-authored, no ML/infra required.
_PERSONA_QUERY_EXPANSION: dict[str, str] = {
    "digital_nomad": "coworking wifi cafe remote work",
    "sports_fitness": "gym trail running fitness training",
    "pet_parent": "dog-friendly pet-friendly park",
    "luxury_traveller": "luxury premium fine dining upscale",
    "budget_backpacker": "budget cheap hostel free street food",
    "senior_traveller": "accessible relaxed comfortable senior-friendly",
}

_PURPOSE_QUERY_EXPANSION: dict[str, str] = {
    "honeymoon": "romantic scenic couples sunset",
    "family_vacation": "kid-friendly family activities",
    "solo_backpacking": "solo traveller budget hostel",
    "business_leisure": "convenient efficient wifi",
    "adventure": "adventure outdoor trekking hiking",
    "group_holiday": "group friends nightlife",
}

# Crowd-dial retrieval bias (hidden-gem curation, docs/GTM_STRATEGY.md §2) —
# same zero-infra query-expansion mechanism as the persona/purpose maps above.
_CROWD_QUERY_EXPANSION: dict[str, str] = {
    "offbeat": "hidden gems off the beaten path quiet local secret underrated",
    "touristy": "top attractions iconic landmarks must-see famous",
    "balanced": "",
}


# ---------------------------------------------------------------------------
# Hybrid lexical pass: BM25 over destination-filtered corpus (docs §3D)
# ---------------------------------------------------------------------------

def _bm25_search_collection_sync(
    client, collection: str, destination: str, query: str, limit: int, max_candidates: int = 500
) -> list[SearchResult]:
    """Keyword/BM25 pass over all points for `destination` in `collection`.

    Pure vector search can miss exact, specific nouns (place names, dish
    names) when their embeddings happen to sit further away than a more
    "generic" chunk. BM25 catches these deterministically via term overlap.
    Scoped to a single destination via Qdrant's `scroll` (not `search`) so
    it works without needing an existing query vector.
    """
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        raise RuntimeError("rank_bm25 not installed. Run: pip install rank_bm25")

    dest_filter = Filter(
        must=[FieldCondition(key="destination", match=MatchValue(value=destination))]
    )
    points, _ = client.scroll(
        collection_name=collection,
        scroll_filter=dest_filter,
        limit=max_candidates,
        with_payload=True,
        with_vectors=False,
    )
    if not points:
        return []

    texts = [(p.payload or {}).get("text", (p.payload or {}).get("text_preview", "")) for p in points]
    tokenized = [t.lower().split() for t in texts]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.lower().split())

    ranked_idx = sorted(range(len(points)), key=lambda i: scores[i], reverse=True)[:limit]
    results = []
    for i in ranked_idx:
        if scores[i] <= 0:
            continue  # no lexical overlap at all — not a useful lexical match
        p = points[i].payload or {}
        results.append(SearchResult(
            text=p.get("text", p.get("text_preview", "")),
            source=p.get("source", collection),
            source_url=p.get("source_url", p.get("post_url", "")),
            score=float(scores[i]),
            destination=p.get("destination", destination),
            published_date=p.get("published_date"),
        ))
    return results


# ---------------------------------------------------------------------------
# Primitive: single-query Qdrant search
# ---------------------------------------------------------------------------

async def semantic_search(
    query: str,
    destination: str,
    limit: int = 10,
    vector: list[float] | None = None,
    bm25_query: str | None = None,
    collections: list[str] | None = None,
) -> list[SearchResult]:
    # embed() is CPU-bound (sentence-transformers) and client.search() is a
    # blocking network call (sync QdrantClient). Both block the asyncio event
    # loop if called inline, which serializes concurrent requests under load.
    # Offload each to a worker thread so the event loop stays free.
    # Callers with multiple queries (e.g. retrieve_context) can pass a
    # precomputed `vector` to batch-embed once instead of one model call per query.
    if vector is None:
        vector = (await asyncio.to_thread(embed, [query]))[0]
    client = get_qdrant()

    dest_filter = Filter(
        must=[FieldCondition(key="destination", match=MatchValue(value=destination))]
    )

    def _search_collection(collection: str):
        return client.search(
            collection_name=collection,
            query_vector=vector,
            query_filter=dest_filter,
            limit=limit // 2,
        )

    # Defaults to wiki+reddit (unchanged behavior for existing callers —
    # itinerary RAG context, the /search endpoint, run_rag_eval.py). Callers
    # that want to additionally draw on youtube_comments (e.g. cost_grounding's
    # community price-mention search) pass `collections` explicitly.
    if collections is None:
        collections = [settings.qdrant_collection_wiki, settings.qdrant_collection_reddit]
    hits_per_collection = await asyncio.gather(
        *[asyncio.to_thread(_search_collection, c) for c in collections]
    )

    semantic_results = []
    for collection, hits in zip(collections, hits_per_collection):
        for hit in hits:
            p = hit.payload or {}
            semantic_results.append(SearchResult(
                text=p.get("text", p.get("text_preview", "")),
                source=p.get("source", collection),
                source_url=p.get("source_url", p.get("post_url", "")),
                score=hit.score,
                destination=p.get("destination", destination),
                published_date=p.get("published_date"),
            ))
    semantic_results.sort(key=lambda r: r.score, reverse=True)

    if not settings.hybrid_search_enabled:
        return semantic_results[:limit]

    # Hybrid: fuse the semantic ranking with a BM25 keyword ranking via RRF.
    # bm25_query defaults to the same text used for embedding, but callers
    # doing HyDE-style query augmentation should pass the original raw query
    # here — BM25 needs literal terms, not a synthesized hypothetical passage.
    lexical_query = bm25_query if bm25_query is not None else query
    bm25_lists = await asyncio.gather(
        *[
            asyncio.to_thread(_bm25_search_collection_sync, client, c, destination, lexical_query, limit)
            for c in collections
        ]
    )
    bm25_flat = [r for sub in bm25_lists for r in sub]
    bm25_flat.sort(key=lambda r: r.score, reverse=True)

    if not bm25_flat:
        return semantic_results[:limit]

    merged = _rrf_merge([semantic_results, bm25_flat])
    return merged[:limit]


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
# Cross-encoder reranking (docs §P3)
# ---------------------------------------------------------------------------

async def _rerank(query: str, results: list[SearchResult], top_n: int = 40) -> list[SearchResult]:
    """Rerank the top `top_n` RRF candidates with a cross-encoder.

    A cross-encoder scores (query, doc) pairs jointly and is meaningfully
    more precise than comparing independently-computed embeddings, at the
    cost of one forward pass per candidate — cheap enough for a ~40-doc
    shortlist, prohibitive for full-corpus retrieval. Best-effort: any
    failure (model download/OOM/etc.) falls back to the incoming RRF order
    rather than breaking retrieval.
    """
    if not results:
        return results
    head, tail = results[:top_n], results[top_n:]
    try:
        texts = [r.text for r in head]
        scores = await asyncio.to_thread(rerank_scores, query, texts)
    except Exception:
        return results

    reranked_head = [
        r.model_copy(update={"score": float(s)})
        for r, s in sorted(zip(head, scores), key=lambda pair: pair[1], reverse=True)
    ]
    return reranked_head + tail


# ---------------------------------------------------------------------------
# High-level retrieval
# ---------------------------------------------------------------------------

async def retrieve_context(trip_config: TripConfig, enable_reranking: bool | None = None) -> list[dict]:
    """
    Retrieve the top-20 context chunks for itinerary generation.

    Runs three query variants in parallel and merges with Reciprocal Rank
    Fusion so both specific terms ("anime cafes") and vibe queries
    ("relaxed cultural experience") are well-covered. Optionally augments
    the vibe query with a HyDE hypothetical passage, fuses semantic +
    BM25 rankings per query (hybrid search), and — when reranking is
    enabled — reranks the merged shortlist with a cross-encoder before
    truncating to top-20.

    `enable_reranking`: cross-encoder reranking adds a second model call
    and measurably increases latency (see load-test results), so it's off
    by default (falls back to `settings.reranking_enabled`, itself False).
    Pass `enable_reranking=True` explicitly for call sites where the extra
    precision is worth the cost — currently only final itinerary generation
    in chains/itinerary_chain.py.
    """
    dest = trip_config.destination.city if trip_config.destination else "general"
    personas = " ".join(trip_config.personas).replace("_", " ") if trip_config.personas else ""
    purpose = getattr(trip_config, "purpose", "") or ""
    pace = getattr(trip_config, "pace", "") or ""

    # Persona/occasion-filtered retrieval (⭐ NEW, free-tools mechanism —
    # design memo Part 1.3 "Mechanism A"): the existing wiki/reddit
    # collections have no persona/attraction_type payload field to filter
    # on (that's the unimplemented §11 unified metadata schema), so instead
    # we bias retrieval toward persona/occasion-relevant content by
    # expanding the query text itself with concrete keywords a persona- or
    # occasion-relevant document would actually contain. Zero infra cost —
    # just better query construction over the same free collections.
    persona_keywords = " ".join(_PERSONA_QUERY_EXPANSION.get(p, "") for p in trip_config.personas).strip()
    purpose_keywords = _PURPOSE_QUERY_EXPANSION.get(purpose.strip().lower(), "")
    crowd_keywords = _CROWD_QUERY_EXPANSION.get(
        getattr(trip_config, "crowd_preference", "balanced"), ""
    )

    raw_queries = [
        # Query 1 — config-oriented: persona + core nouns (+ persona keyword expansion)
        f"{dest} travel {personas} {persona_keywords} highlights activities food".strip(),
        # Query 2 — purpose/vibe: what kind of trip (+ occasion & crowd-dial keyword expansion)
        f"things to do in {dest} {purpose} {purpose_keywords} {crowd_keywords} {pace} trip hidden gems local tips".strip(),
        # Query 3 — practical: logistics, advice, warnings
        f"{dest} best restaurants sightseeing transport safety advice",
    ]

    # HyDE (§3G): embed a synthesized "ideal passage" for the vibe query
    # instead of the raw sparse query text — dense prose embeds closer to
    # real guide/forum content than a keyword-ish query does. BM25 still
    # uses the original raw query text (passed as bm25_query below), since
    # lexical matching needs literal terms, not synthesized prose.
    embed_queries = list(raw_queries)
    if settings.hyde_enabled:
        embed_queries[1] = generate_hypothetical_passage(dest, purpose, pace, trip_config.personas)

    # Batch-embed all 3 query variants in a single model call instead of one
    # embed() call per query — sentence-transformers batches efficiently, so
    # this cuts model invocation overhead ~3x versus embedding one at a time.
    vectors = await asyncio.to_thread(embed, embed_queries)

    result_lists = await asyncio.gather(
        *[
            semantic_search(embed_queries[i], dest, limit=15, vector=vectors[i], bm25_query=raw_queries[i])
            for i in range(len(raw_queries))
        ]
    )

    merged = _rrf_merge(list(result_lists))

    should_rerank = settings.reranking_enabled if enable_reranking is None else enable_reranking
    if should_rerank:
        # Anchor reranking on all three raw query facets combined (config +
        # vibe + practical) rather than a single variant — a cross-encoder
        # anchored on just the vibe query can under-rank docs that are
        # specifically about safety/practical topics.
        rerank_anchor = " ".join(raw_queries)
        merged = await _rerank(rerank_anchor, merged, top_n=40)

    merged = merged[:20]

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
# Itinerary-corpus few-shot retrieval (docs/rag-strategy.md §9 "Injection into
# LLM Prompt") — retrieves 2-3 real traveller itineraries matching the user's
# trip config from the two-named-vector `itinerary_corpus` collection.
# ---------------------------------------------------------------------------

# Below this weighted-similarity floor a "match" is usually a different trip
# shape entirely (wrong duration/purpose) — injecting it would mislead more
# than ground. §9 suggests 0.72 for a config-only search; the floor here is
# lower because the 60/40 config+content merge dilutes the config score.
_CORPUS_MIN_SCORE = 0.45


def _corpus_group_type(group) -> str:
    """Map GroupComposition onto the corpus payload's group_type vocabulary
    (solo | couple | family | friends | group)."""
    total_adults = group.adults + group.seniors
    if group.has_kids or group.has_infants:
        return "family"
    if total_adults == 1:
        return "solo"
    if total_adults == 2:
        return "couple"
    return "group"


def _corpus_duration_days(dates: dict | None) -> int | None:
    if not dates:
        return None
    if dates.get("duration_days"):
        return int(dates["duration_days"])
    start, end = dates.get("start"), dates.get("end")
    if start and end:
        try:
            d = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days + 1
            return d if d > 0 else None
        except ValueError:
            return None
    return None


def _corpus_config_query(trip_config: TripConfig) -> str:
    """Mirror of the ingest-side `_config_text()` in
    chains/itinerary_corpus_extraction_chain.py — the query must live in the
    same embedding space as the stored config vectors, e.g.
    '5 day moderate cultural couple trip Kyoto Japan'."""
    dest = trip_config.destination
    duration = _corpus_duration_days(trip_config.dates)
    parts = [
        f"{duration} day" if duration else "",
        trip_config.effective_pace(),
        trip_config.purpose or "",
        _corpus_group_type(trip_config.group),
        "trip",
        dest.city if dest else "",
        dest.country if dest else "",
    ]
    return " ".join(p for p in parts if p).strip()


def _format_corpus_days_brief(days: list[dict], max_days: int = 8) -> str:
    lines = []
    for day in days[:max_days]:
        places = ", ".join(day.get("places", []))
        line = f"Day {day.get('day_number')}: {day.get('theme', '')}. Places: {places}."
        tips = day.get("tips", "")
        if tips:
            line += f" Tip: {tips}"
        lines.append(line)
    return "\n".join(lines)


async def retrieve_itinerary_examples(trip_config: TripConfig, limit: int = 3) -> str:
    """Retrieve up to `limit` real traveller itineraries as few-shot grounding
    for generation (docs §9). Returns a prompt-ready string, or "" when the
    corpus has no usable match — callers treat "" as "skip the section".

    Both named vectors are queried with the same config-style query embedding
    and merged 60% config / 40% content per the §9 embedding strategy, then
    weighted by each document's source-authority `quality_score`.
    """
    if not settings.itinerary_corpus_retrieval_enabled:
        return ""
    if not trip_config.destination or not trip_config.destination.city:
        return ""

    query = _corpus_config_query(trip_config)
    vector = (await asyncio.to_thread(embed, [query]))[0]
    client = get_qdrant()
    city = trip_config.destination.city

    dest_filter = Filter(
        must=[FieldCondition(key="destination", match=MatchValue(value=city))]
    )

    def _search_named(vector_name: str, use_filter: bool):
        return client.search(
            collection_name=settings.qdrant_collection_itinerary_corpus,
            query_vector=(vector_name, vector),
            query_filter=dest_filter if use_filter else None,
            limit=limit * 2,
            with_payload=True,
        )

    config_hits, content_hits = await asyncio.gather(
        asyncio.to_thread(_search_named, "config", True),
        asyncio.to_thread(_search_named, "content", True),
    )

    # The extraction LLM writes free-form destination names ("Kyoto" vs
    # "kyoto"), so an exact payload filter can miss legitimate matches.
    # Fall back to an unfiltered search + case-insensitive client-side check
    # rather than silently injecting a different city's itinerary.
    if not config_hits and not content_hits:
        config_hits, content_hits = await asyncio.gather(
            asyncio.to_thread(_search_named, "config", False),
            asyncio.to_thread(_search_named, "content", False),
        )
        city_lower = city.strip().lower()
        config_hits = [h for h in config_hits if ((h.payload or {}).get("destination") or "").strip().lower() == city_lower]
        content_hits = [h for h in content_hits if ((h.payload or {}).get("destination") or "").strip().lower() == city_lower]

    # 60/40 config/content weighted merge (docs §9), then source-authority
    # weighting so a high-karma trip report outranks a low-signal blog at
    # equal similarity.
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
        source = p.get("source_name") or "traveller report"
        examples.append(
            f"[Source: {source}{' — ' + header if header else ''}]\n"
            + _format_corpus_days_brief(days)
        )

    return "\n\n---\n\n".join(examples)


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
