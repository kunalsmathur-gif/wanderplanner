# WanderPlanner — RAG Strategy: Current State, Gaps & Roadmap
**Version:** 4.0 · **Date:** June 2026 · **Updated:** July 2, 2026

---

## 1. Are We Using RAG Today?

**Yes — fully wired into production, and substantially upgraded as of v5.3.**

WanderPlanner has a RAG infrastructure in place (Qdrant + `all-MiniLM-L6-v2` embeddings). All retrieval paths — including the primary **Gemini** production path — now call `retrieve_context()`. The previous silent bypass has been fixed, a hidden concurrency bug that serialized retrieval under load has been fixed, and the hybrid search / HyDE / reranking / OSM ingestion / itinerary-cache items that were "pending" in the v3.0 roadmap are now implemented.

### What's Wired Up (Current)

```
Data Sources                Qdrant Collections           Where Used
─────────────────────       ──────────────────           ──────────────────────
Wikivoyage (on-demand) ──▶  wiki (384-dim)  ─────────▶  retrieve_context() → Gemini/Groq/Ollama prompt
Reddit (every 6 hours) ──▶  reddit (384-dim) ─────────▶  retrieve_context() + /api/reddit-highlights
OSM POIs (weekly)      ──▶  osm_pois (384-dim)  ──────▶  RAG-skeleton fallback (Tier 2) + future itinerary grounding
Itinerary generations  ──▶  itinerary_cache (384-dim) ─▶  Fallback Tier 1 (cache-hit, cosine ≥ 0.88)
```

### Component RAG Status

| Component | RAG used? | Notes |
|---|---|---|
| Gemini itinerary generation | ✅ Yes | Multi-query hybrid (BM25+semantic) RRF + HyDE + cross-encoder rerank + summarised context injected |
| Groq/Ollama itinerary generation | ✅ Yes | Now uses the same `retrieve_context()` + `summarise_context()` pipeline as Gemini (previously bypassed summarisation — fixed) |
| Anya wizard chat | ❌ No | Still relies on Gemini parametric memory |
| City recommender | ❌ No | LLM-only |
| Destination comparison | ❌ No | LLM-only |
| Best time (seasonal data) | ⚠️ Partial | Scrapes Wikivoyage live — not yet cached in Qdrant |
| Reddit tagging | ✅ Fixed | `_extract_destination()` now matches against 200+ known destinations |
| Itinerary fallback (LLM down) | ✅ New | 3-tier fallback chain: cache → RAG skeleton (OSM POIs) → enhanced mock |

---

## 2. How Is It Leveraged Today?

### Itinerary Generation (all providers)
```python
# services/search.py
async def retrieve_context(trip_config, enable_reranking: bool | None = None) -> list[dict]:
    # Runs 3 query variants in parallel. Query 2 (vibe/purpose) is replaced
    # with a HyDE hypothetical passage before embedding when hyde_enabled.
    raw_queries = [
        f"{dest} travel {personas} highlights activities food",
        f"things to do in {dest} {purpose} {pace} trip hidden gems local tips",
        f"{dest} best restaurants sightseeing transport safety advice",
    ]
    embed_queries = [... HyDE passage for query 2 if enabled ...]
    vectors = await asyncio.to_thread(embed, embed_queries)   # batched, offloaded to a worker thread
    result_lists = await asyncio.gather(*[
        semantic_search(embed_queries[i], dest, limit=15, vector=vectors[i], bm25_query=raw_queries[i])
        for i in range(3)
    ])
    merged = _rrf_merge(result_lists)
    if should_rerank:   # settings.reranking_enabled OR explicit enable_reranking=True
        merged = await _rerank(" ".join(raw_queries), merged, top_n=40)   # cross-encoder, offloaded to a worker thread
    return merged[:20]

# itinerary_chain.py (Gemini + Groq/Ollama paths)
context_docs = await retrieve_context(trip_config, enable_reranking=True)
context_text = summarise_context(context_docs, max_chars=2400)   # ~600 tokens
# Injected as {context} in SYSTEM_PROMPT
```
Each `semantic_search()` call now *also* fuses in a BM25 keyword pass (`_bm25_search_collection_sync`, scoped to the destination via Qdrant `scroll`) via Reciprocal Rank Fusion, so specific nouns ("anime cafes", "Tsukiji") are caught even when their embeddings aren't the closest semantic match. The 20 RRF-merged (and optionally reranked) chunks are compressed through `summarise_context()` before injection — time-decay applied, deduplicated by Jaccard similarity, sorted by decayed score, capped at 2400 chars (~600 tokens).

**Reranking is scoped, not global.** Cross-encoder reranking (`sentence-transformers` `CrossEncoder`) adds real measured latency — load testing showed throughput drop from ~23.6 req/s to ~7 req/s at concurrency=50 with reranking on everywhere. It's therefore **off by default** (`settings.reranking_enabled = False`) and explicitly turned on only at the two real itinerary-generation call sites in `chains/itinerary_chain.py` via `retrieve_context(trip_config, enable_reranking=True)`. Lighter-weight paths (the direct `/api/search` endpoint, and the Tier-3 fallback's tip-gathering call) use the fast default.

**Concurrency bug fixed.** Both `embed()` (sentence-transformers, CPU-bound) and `QdrantClient.search()`/`scroll()` (sync client) used to be called directly inside `async def` functions with no executor offload — meaning `asyncio.gather()` over "parallel" queries actually serialized on the event loop (throughput flatlined at ~10 req/s regardless of concurrency). Fixed by wrapping every blocking call in `asyncio.to_thread()`. Post-fix, retrieval also batch-embeds all 3 query variants in a single model call instead of 3 separate ones.

### Reddit Highlights (UI component)
```python
# routers/reddit_highlights.py
vector = embed([f"{destination} travel tips guide best places"])[0]
hits = client.search(collection_name="reddit", query_vector=vector, limit=10)
```
Now returns properly destination-tagged posts thanks to the fixed `_extract_destination()`.

### What's Still Missing from the Pipeline
1. **No Wikivoyage Qdrant cache for best-time** — still live-scraped on every request
2. **No Anya wizard RAG** — city suggestions rely on Gemini parametric memory alone
3. **No visa/entry-rules collection** — not yet ingested
4. **No `itinerary_corpus` / `generated_itineraries` learning flywheel** — described in §9/§10 below, not yet built

---

## 3. Implemented Improvements (v5.2 → v5.3)

### 3A — Gemini Path Now Uses RAG ✅ DONE

```python
# itinerary_chain.py — _gemini_itinerary()
context_docs = await retrieve_context(trip_config)
context_text = summarise_context(context_docs, max_chars=2400)
prompt = SYSTEM_PROMPT.format(context=context_text, trip_config=trip_json)
```

### 3B — Better Chunking ✅ DONE

| Source | Before | After |
|---|---|---|
| Wikivoyage | 1 chunk per section, hard 1500-char cut | N chunks per section at sentence boundaries, ~500 chars each |
| Reddit | 1 chunk per post (title + 800-char body) | 1 chunk per paragraph (`\n\n` split), each prefixed with title |

```python
# wikivoyage.py — _sentence_boundary_chunks()
def _sentence_boundary_chunks(text: str, max_chars: int = 500) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    # Accumulate sentences until max_chars, then start new chunk
    return [c for c in chunks if len(c) > 80]

# reddit.py — _chunk_reddit_post()
def _chunk_reddit_post(title: str, selftext: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', selftext) if len(p.strip()) >= 80]
    return [f"{title}. {para}" for para in paragraphs]
```

### 3C — Context Summarisation ✅ DONE

```python
def summarise_context(docs: list[dict], max_chars: int = 2400) -> str:
    # 1. Apply time-decay to scores
    # 2. Drop decayed score < 0.35
    # 3. Deduplicate by Jaccard word overlap (> 0.60 → keep highest scored)
    # 4. Sort by decayed score DESC
    # 5. Truncate at 2400 chars (~600 tokens)
```
**Token savings:** Context injection drops from ~7,500 tokens (20 raw chunks) to ~600 tokens — a **12× reduction**.

### 3D — Multi-Query Retrieval with Reciprocal Rank Fusion ✅ DONE

Three parallel queries are run per request and merged with RRF (k=60):

```python
queries = [
    f"{dest} travel {personas} highlights activities food",      # config-oriented
    f"things to do in {dest} {purpose} {pace} hidden gems",     # vibe/purpose
    f"{dest} best restaurants sightseeing transport safety",     # practical
]
result_lists = await asyncio.gather(*[semantic_search(q, dest, limit=15) for q in queries])
merged = _rrf_merge(result_lists)  # RRF score = Σ 1/(k + rank_i)
```

### 3E — Time-Decay Scoring ✅ DONE

```python
def _time_decay_score(base_score: float, published_date: str | None) -> float:
    """Half-life: 18 months. Floor: 40% of base score."""
    decay = 0.5 ** (age_days / 548)
    return base_score * (0.4 + 0.6 * decay)
```

| Content age | Score multiplier |
|---|---|
| 1 month | 0.978× |
| 1 year | 0.778× |
| 3 years | 0.550× |
| Unknown date | 0.850× |

Reddit posts now store `published_date` from `created_utc` in the Qdrant payload.

### 3F — Reddit Destination Tagging ✅ DONE

```python
def _extract_destination(title: str, selftext: str) -> str:
    for text in (title, selftext):
        for dest_lower, dest_canonical in _DEST_LOWER.items():
            if re.search(r'\b' + re.escape(dest_lower) + r'\b', lower):
                return dest_canonical
    return "general"
```
Regex word-boundary matching against 200+ canonical destination names. `"Balinese culture"` correctly returns `"general"` (not `"Bali"`).

---

### 3B — Better Chunking (Smaller, Cleaner)

| Current | Recommended |
|---|---|
| 1,500-char hard cuts | 400–600 char chunks with sentence boundaries |
| Entire Wikivoyage sections | Split at paragraph level with section tag preserved |
| Reddit posts as-is | Title + first 300 chars of body as separate chunk |

Smaller chunks = higher cosine precision = fewer irrelevant chunks retrieved.

### 3C — Context Summarisation Before Injection

Instead of injecting raw chunks, summarise them first:
```python
def _summarise_context(docs: list[dict], max_tokens: int = 600) -> str:
    """
    Deduplicate + rank + truncate to a fixed budget.
    1. Remove chunks with cosine score < 0.35
    2. Deduplicate by sentence overlap (jaccard > 0.6 → keep highest score)
    3. Sort by score DESC
    4. Truncate at max_tokens chars (~150 words)
    """
```
**Token savings:** Context injection drops from ~7,500 tokens to ~600 tokens — a ~12× reduction in context cost.

### 3D — Hybrid Search: BM25 + Semantic ✅ DONE

Pure vector search struggles with **specific nouns** — "Tokyo" vs "Kyoto" may have similar embeddings but must be treated as hard filters. The fix layers keyword matching on top of semantic search, now live in `services/search.py`:

```python
# services/search.py — actual implementation
from rank_bm25 import BM25Okapi

def _bm25_search_collection_sync(client, collection, destination, query, limit, max_candidates=500):
    # Scoped to the destination via Qdrant scroll (not search — no query vector needed)
    dest_filter = Filter(must=[FieldCondition(key="destination", match=MatchValue(value=destination))])
    points, _ = client.scroll(collection_name=collection, scroll_filter=dest_filter,
                               limit=max_candidates, with_payload=True, with_vectors=False)
    tokenized = [(p.payload or {}).get("text", "").lower().split() for p in points]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.lower().split())
    # ... build SearchResult list from the top-scoring points ...

# Inside semantic_search(): both a BM25 pass and a semantic pass are run
# concurrently per collection, then fused via the existing _rrf_merge().
```

Differences from the original proposal: rather than requiring an in-memory `corpus` list, the implementation scrolls the destination-filtered slice directly from Qdrant (bounded to 500 candidates), so it works against the live collections without a separate corpus data structure. It's applied to **every** `semantic_search()` call (wiki + reddit), gated by `settings.hybrid_search_enabled` (default `True`).

**Measured effect:** on the golden dataset (see `docs/eval-set.md` §4T), hybrid search widens the candidate pool (Precision@10 dropped slightly, from 0.21 → 0.18, since more lexically-related-but-off-topic chunks now surface) while Recall@10 held at a perfect 1.00. In production this trades a small amount of top-of-list purity for materially better handling of proper nouns.

### 3E — Time-Decay Scoring (New)

Travel data expires. A 2021 blog post recommending a now-closed restaurant is worse than useless — it actively degrades output quality.

```python
from datetime import datetime, timezone

def _time_decay_score(base_score: float, published_date: str | None) -> float:
    """
    Apply exponential decay based on content age.
    Half-life: 18 months (travel info stays reasonably current for ~18 months)
    """
    if not published_date:
        return base_score * 0.85  # unknown date → moderate penalty

    try:
        pub = datetime.fromisoformat(published_date).replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - pub).days
        half_life_days = 548  # 18 months
        decay = 0.5 ** (age_days / half_life_days)
        return base_score * (0.4 + 0.6 * decay)  # floor at 40% of base score
    except Exception:
        return base_score * 0.85

# Applied in reranking step after retrieval
ranked = sorted(hits, key=lambda h: _time_decay_score(h.score, h.payload.get("published_date")), reverse=True)
```

Impact: A top-scoring chunk from 2019 drops to ~50% weight; one from last month retains ~95%.

### 3F — Semantic Chunking (New)

Splitting at arbitrary character counts cuts sentences mid-thought and loses section context. Split by **logical boundaries** instead:

```python
def semantic_chunk(text: str, source_type: str) -> list[dict]:
    """Split by logical section boundaries, not character count."""
    if source_type == "blog":
        # Split on markdown/HTML headers: ## Where to Eat, ### Day 1
        sections = re.split(r'\n#{1,3} ', text)
    elif source_type == "reddit":
        # Each top-level comment is its own chunk (natural opinion unit)
        sections = text.split("\n\n---\n\n")
    elif source_type == "wikivoyage":
        # Already section-based from scraper — pass through
        sections = [text]
    elif source_type == "youtube":
        # Concatenate every 5 timestamped segments into one chunk
        lines = text.strip().split("\n")
        sections = [" ".join(lines[i:i+5]) for i in range(0, len(lines), 5)]
    else:
        # Fallback: sentence-boundary split at ~500 chars
        sections = _sentence_boundary_split(text, max_chars=500)

    return [s.strip() for s in sections if len(s.strip()) > 80]  # min viable chunk length


def _sentence_boundary_split(text: str, max_chars: int = 500) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) > max_chars and current:
            chunks.append(current.strip())
            current = s
        else:
            current += " " + s
    if current:
        chunks.append(current.strip())
    return chunks
```

### 3G — Query Augmentation (HyDE) ✅ DONE

Instead of embedding the raw query, `services/hyde.py` synthesizes a plausible-looking travel-guide passage and embeds *that*:
```python
# services/hyde.py — actual implementation (template-based, no LLM round-trip)
def generate_hypothetical_passage(destination, purpose="", pace="", personas=None) -> str:
    persona_bits = [_PERSONA_HOOKS[p] for p in (personas or []) if p in _PERSONA_HOOKS]
    sentence = (
        f"Top things to do and see in {destination} for a {purpose} trip, {pace_bit}. "
        f"Includes hidden gems away from the crowds, local tips on where to eat, "
        f"and practical advice on getting around safely."
    )
    if persona_bits:
        sentence += " Especially good for travelers looking for " + ", ".join(persona_bits) + "."
    return sentence

# In retrieve_context(): applied only to the vibe/purpose query variant.
# BM25 still uses the original raw query text (passed separately as bm25_query)
# since lexical matching needs literal terms, not synthesized prose.
```
**Deliberate scope decision:** implemented as a deterministic template (persona/pace/purpose hooks), not an LLM-generated hypothetical document. This keeps retrieval latency and failure modes unchanged (no extra network call per request) while still moving the query into "prose passage" embedding space. An LLM-generated HyDE passage remains a possible future upgrade if template coverage proves insufficient for very niche personas. Gated by `settings.hyde_enabled` (default `True`).

### 3H — Fix Reddit Destination Tagging

```python
# scrapers/reddit.py — replace naive _extract_destination
def _extract_destination(title: str, selftext: str) -> str:
    # Use a lightweight NER or regex list of 500 popular travel destinations
    # match against title first, then selftext
    for dest in KNOWN_DESTINATIONS:
        if dest.lower() in title.lower():
            return dest
    return "general"
```
This makes the destination filter in `semantic_search()` reliable — currently every Reddit post is tagged `"general"` and the filter matches nothing.

### 3I — Ingest OSM POIs ✅ DONE

`scrapers/osm.py` fetches real POIs (lat/lon, name, category, tags) per destination from the free Overpass API — no API key required. Geocodes the destination via the existing `geocode_city()` service, queries a bounding radius (default 5km, capped at 60 results), skips unnamed/duplicate nodes, embeds a short natural-language description per POI, and upserts into `osm_pois`. Wired into `core/scheduler.py` for a weekly refresh across the ~100 destinations in `KNOWN_DESTINATIONS` (2s delay between destinations to stay polite to the free service). Currently consumed by the Tier 2 RAG-skeleton fallback (§4); direct itinerary-grounding use (use case #1 in §6) is a natural next step once enough destinations are ingested.

### 3J — Cross-Encoder Reranking ✅ DONE (scoped to itinerary generation)

`services/search.py::_rerank()` reranks the top-40 RRF-merged candidates with `cross-encoder/ms-marco-MiniLM-L-6-v2`, scoring `(query, doc)` pairs jointly for materially better precision than comparing independently-computed embeddings. Best-effort: any failure (model load error, OOM) falls back to the incoming RRF order rather than breaking retrieval.

**Off by default, on for itinerary generation only.** A cross-encoder forward pass per candidate is real added latency — load testing showed throughput drop from ~23.6 req/s to ~7 req/s at concurrency=50 with reranking always on. `settings.reranking_enabled` defaults to `False`; `retrieve_context()` accepts an `enable_reranking` override, explicitly set to `True` only at the Gemini and Groq/Ollama itinerary-generation call sites in `chains/itinerary_chain.py`, where the extra precision is worth the cost (LLM latency already dominates the request). Lighter-weight callers (`/api/search`, Tier-3 fallback tip-gathering) use the fast default.

### 3K — Concurrency Fix: Blocking Calls Offloaded to Worker Threads ✅ DONE

Both `embed()` (sentence-transformers, CPU-bound) and the sync `QdrantClient`'s `.search()`/`.scroll()` calls were previously invoked directly inside `async def` functions with no executor offload. This meant `asyncio.gather()` over the "3 parallel query variants" didn't actually run in parallel — everything serialized on the single-threaded event loop. A load test (`apps/api/load_test_rag.py`) confirmed this empirically: throughput flatlined at ~10 req/s regardless of concurrency level (1 → 50), and p50 latency scaled ~46× from concurrency 1 to 50.

**Fix:** every blocking call (`embed`, `client.search`, `client.scroll`) is now wrapped in `asyncio.to_thread()`. Additionally, `retrieve_context()` batch-embeds all 3 query variants in a single `embed()` call instead of 3 separate ones (sentence-transformers batches efficiently). Post-fix throughput at concurrency=50 improved from ~10 → ~23.6 req/s before hybrid/HyDE/reranking were layered back on top (which add their own, expected, additional cost — see §3J).

---

## 4. RAG as Fallback for Real-Time API Failures ✅ DONE

### Current Fallback Behaviour
When the LLM call fails (Gemini after its internal retries, or Groq/Ollama raises), `chains/itinerary_chain.py::generate_itinerary()` now runs a 3-tier RAG-powered fallback chain (`_fallback_itinerary()`) instead of failing the request outright:
- Wizard → smart mock (asks next missing field — context-aware but static) — **unchanged, out of scope this round**
- Itinerary → cache → RAG skeleton → enhanced mock (below)

### RAG-Powered Fallback Strategy — Implemented

#### Tier 1: Cached LLM Response ✅ DONE
`services/itinerary_cache.py`. Every successful LLM-generated itinerary is stored (best-effort, never blocks the response) keyed by an embedding of `f"{dest} {duration}d {pace} {purpose} trip"`:
```python
# services/itinerary_cache.py — actual implementation
async def get_cached_itinerary(trip_config) -> dict | None:
    query = _cache_key_text(trip_config)
    vector = (await asyncio.to_thread(embed, [query]))[0]
    hits = await asyncio.to_thread(lambda: client.search(
        collection_name=settings.qdrant_collection_itinerary_cache,
        query_vector=vector, limit=1, score_threshold=settings.itinerary_cache_score_threshold))  # 0.88
    if not hits:
        return None
    return json.loads(hits[0].payload["itinerary_json"])

async def store_itinerary(trip_config, itinerary_raw) -> None:
    # Best-effort — wrapped in try/except, never raises.
    # Skips storing fallback-generated itineraries (keys starting with "_")
    # so a degraded skeleton/mock can never poison the cache.
    ...
```
Difference from the original proposal: rather than pre-generating itineraries for a fixed top-50 list, the cache is populated organically as real requests succeed — any subsequent semantically-similar request (same destination/duration/pace/purpose) becomes a fast-path fallback candidate.

#### Tier 2: RAG-assembled itinerary skeleton ✅ DONE
`services/rag_fallback.py::rag_skeleton_itinerary()`. If the cache misses:
```python
async def rag_skeleton_itinerary(trip_config) -> dict | None:
    # 1. Scroll osm_pois for this destination (min 3 POIs required, else return None → Tier 3)
    # 2. Slot POIs round-robin into day structure by pace (relaxed=3, moderate=4, packed=5 items/day)
    # 3. Return a valid raw itinerary dict — no LLM call, real venue names + real lat/lon
```
Returns `None` (falls through to Tier 3) when fewer than 3 OSM POIs are ingested for the destination — avoids building a near-empty, unconvincing plan.

#### Tier 3: Smart mock with RAG context ✅ DONE
`chains/itinerary_chain.py::_mock_itinerary(trip_config, tip_texts=...)`. If Tier 2 also declines, `_fallback_itinerary()` pulls a handful of real retrieved wiki/reddit snippets via `retrieve_context()` and splices them into the static mock's item descriptions as "Local tip: ..." — reads far less like a generic placeholder than the pre-v5.3 hardcoded mock, even when no OSM data exists yet for that destination.

### Failure → Fallback Decision Tree — as implemented

```
LLM call (Gemini / Groq / Ollama)
    │
    ├─ Success ──────────────────────────────────────▶  Return itinerary; store_itinerary() caches it (best-effort)
    │
    └─ Exception (after internal retries/backoff)
            │
            ├─ get_cached_itinerary() — cosine ≥ 0.88  ──▶  Hit → return cached itinerary instantly
            │
            ├─ Cache miss → rag_skeleton_itinerary() — needs ≥3 osm_pois for destination
            │       │
            │       ├─ Enough POIs → real-venue skeleton itinerary, no LLM call
            │       │
            │       └─ Not enough POIs → Tier 3
            │
            └─ _mock_itinerary(tip_texts=retrieved wiki/reddit snippets) — always succeeds
```

Unit-tested in `tests/unit/test_rag.py::test_fallback_tier1_cache_hit`, `test_fallback_tier2_rag_skeleton_builds_from_osm_pois`, `test_fallback_tier3_enhanced_mock_splices_real_tips` (and their negative-path counterparts).

---

## 5. Current RAG Pipeline Architecture

```
INGESTION PIPELINE (offline / scheduled)
─────────────────────────────────────────
Wikivoyage ──▶ Scrape sections ──▶ Sentence-boundary chunks (~500 chars) ──▶ Embed ──▶ Qdrant [wiki]
Reddit     ──▶ Top posts (6hr)  ──▶ Paragraph chunks (≥80 chars, title prefix) ──▶ Embed ──▶ Qdrant [reddit]
OSM POIs   ──▶ Overpass API (weekly) ──▶ {name,type,coords} ✅ DONE ──▶ Qdrant [osm_pois]
Itinerary  ──▶ Post-generation  ──▶ Cache trips on success ✅ DONE ──▶ Qdrant [itinerary_cache]
Visa/Entry ──▶ Static JSON      ──▶ Per country rules    ⚠️ NOT YET BUILT ──▶ Qdrant [visa_info]


RETRIEVAL PIPELINE (per request) — as of v5.3
─────────────────────────────────────────────
User trip config
    │
    ├─ 3 parallel query variants (config / vibe / practical) — vibe variant run through HyDE ✅
    │       │
    │       ▼
    ├─ Hybrid search per collection: BM25 (Qdrant scroll) + semantic cosine (wiki + reddit, limit=15 each) ✅
    │       │
    │       ▼
    ├─ Reciprocal Rank Fusion (k=60) — merge BM25 + semantic rankings, then merge 3 query variants
    │       │
    │       ▼
    ├─ [Only for itinerary generation] Cross-encoder reranking (ms-marco-MiniLM-L-6-v2, top-40) ✅
    │       │
    │       ▼
    ├─ Time-decay scoring (half-life 18 months, floor 40%)
    │       │
    │       ▼
    ├─ Score filter (decayed score < 0.35 → drop)
    │       │
    │       ▼
    ├─ Jaccard deduplication (>0.60 word overlap → keep higher-scored)
    │       │
    │       ▼
    ├─ Sort by decayed score DESC
    │       │
    │       ▼
    ├─ Truncate at 2400 chars (~600 tokens)
    │       │
    │       ▼
    └─ Inject into LLM prompt {context}

    (On LLM failure: cache lookup → OSM-grounded skeleton → RAG-tipped mock — see §4)
```

---

## 6. Use Cases RAG Can Power in WanderPlanner

| # | Use Case | Collections | Value |
|---|---|---|---|
| 1 | **Itinerary grounding** | wiki + osm_pois | Real POI names, correct lat/lon, no hallucinated venues |
| 2 | **Wizard destination chips** | wiki + osm_pois | When user says "Sri Lanka", Anya suggests Colombo/Galle/Kandy with reasons from real content |
| 3 | **Real-time traveller sentiment** | reddit | "Heads up — recent Reddit posts flag tourist scams near this area" |
| 4 | **Budget estimates from community data** | reddit | "r/solotravel users report ₹2,500/day in Bali for mid-range" |
| 5 | **Seasonal/festival injection** | wiki + events | Automatically add Diwali festival context if dates overlap |
| 6 | **Itinerary fallback (API down)** ✅ DONE | itinerary_cache + osm_pois | Valid day plan without LLM call (see §4) |
| 7 | **Visa & entry rules** | visa_info | "Indians need visa on arrival for Thailand — ₹2,500 approx" |
| 8 | **Safety advisories** | reddit + wiki | Flag destinations with recent negative posts (score-weighted) |
| 9 | **Food & dietary context** | wiki + reddit | Inject veg-friendly restaurant names for users who selected "Pure veg food" |
| 10 | **Post-gen chat refinements** | itinerary_cache | Anya answers "what's near Day 2's temple?" from RAG, not LLM parametric memory |

---

## 7. Token Cost Impact

| Scenario | Before v5.2 | After v5.2 | Savings |
|---|---|---|---|
| Itinerary prompt context | ~7,500 tokens (20 raw chunks) | ~600 tokens (summarised) | ~87% reduction |
| Gemini path RAG | 0 tokens (not wired) | ~600 tokens | New capability |
| Wizard (with destination grounding) | 0 tokens (no RAG) | ~200 tokens (top-3 POIs, future) | Planned |
| Per session total (Gemini 2.5 Flash) | ~$0.007 | ~$0.003 | ~57% |
| At 10,000 sessions/month | ~$70 | ~$30 | ~$40/mo |

---

## 8. Implementation Priority

| Priority | Task | Status | Impact |
|---|---|---|---|
| P0 | Wire `retrieve_context()` into `_gemini_itinerary()` | ✅ Done | Grounds all production itineraries |
| P0 | Fix Reddit `_extract_destination()` with keyword list | ✅ Done | Makes Reddit destination filter reliable |
| P1 | Context summarisation (`summarise_context()`) | ✅ Done | 87% token reduction |
| P1 | Wikivoyage sentence-boundary chunking (~500 chars) | ✅ Done | Higher retrieval precision |
| P1 | Reddit paragraph-level chunking + `published_date` | ✅ Done | Paragraph-granularity chunks, time-decay enabled |
| P1 | Multi-query (3 variants) + Reciprocal Rank Fusion | ✅ Done | Better recall for vibe/niche/practical queries |
| P1 | Time-decay scoring (18-month half-life) | ✅ Done | Stale content penalised at retrieval |
| P1 | Async concurrency fix (`asyncio.to_thread` + batch embed) | ✅ Done | Throughput ~10 → ~23.6 req/s @ concurrency=50 |
| P1 | OSM POI ingestor (Overpass API) | ✅ Done | Real coordinates; eliminates hallucinated lat/lon |
| P1 | Hybrid BM25 + semantic search | ✅ Done | Better handling of proper nouns/specific terms |
| P2 | `itinerary_cache` collection + cache hit logic | ✅ Done | Fallback + free repeat visits |
| P2 | Golden dataset + automated eval (`run_rag_eval.py`) | ✅ Done | Recall@10=1.00, MRR≈0.85-0.94, nDCG@10≈0.89-0.96 |
| P2 | Visa info collection + wizard injection | ❌ Pending | Practical user value |
| P2 | HyDE query augmentation | ✅ Done | Better recall for niche personas (template-based) |
| P3 | Cross-encoder reranker | ✅ Done | Scoped to itinerary generation only (latency-gated) |

---

## 9. Web-Scraped Itinerary Corpus Pipeline

### Concept

Scrape real, human-authored itineraries from travel blogs, forums, and social media. Extract them into a structured format, embed them, and store in a new `itinerary_corpus` Qdrant collection. When a user asks for a Tokyo 7-day trip, the LLM receives 2–3 real itineraries from other travellers as grounding — the output is built on patterns that actually worked, not just training data.

This is fundamentally different from the existing wiki/reddit collections:
- **Wiki/Reddit** → unstructured tips, advice, sentiment ("Avoid Patong Beach in peak season")
- **Itinerary corpus** → structured day-by-day plans ("Day 1: Senso-ji → Akihabara → Shibuya crossing")

### Data Sources & Scraping Strategy

**Phase v0 — Free, friction-free sources (build the pipeline first):**

| Source | Content type | Scrape method | Cost | Refresh |
|---|---|---|---|---|
| **Nomadic Matt / The Planet D** | Blog itineraries with day breakdowns | `feedparser` (RSS) + `BeautifulSoup` for full page | Free | Monthly |
| **Lonely Planet** (lonelyplanet.com/itineraries) | Structured `n-day` itinerary pages | `httpx` + BeautifulSoup; `<section>` tags are clean | Free | Monthly |
| **Wikivoyage** | Authoritative destination guides | Official **Wikimedia API** (`action=parse`) — structured, stable, no scraping | Free | Quarterly |
| **Reddit trip reports** (r/travel, r/solotravel, r/indiatravel) | "My X-day trip to Y" self-posts | **PRAW** (`praw` library, OAuth, 100 req/min free) — filter `flair:trip-report`; grab post + top 5 parent comments | Free | Daily |
| **YouTube captions** | Travel vlog day-by-day descriptions | **`youtube-transcript-api`** — extracts manual/auto-generated captions by video ID; **no API key needed** | Free | Weekly |

**Phase v1 — Premium, high-fidelity sources (add after v0 pipeline is stable):**

| Source | Content type | Scrape method | Cost | Refresh |
|---|---|---|---|---|
| **TripAdvisor** (reviews, ratings) | Current ratings, user reviews, recent tips | **Apify** / **Bright Data** / ScrapeLabs with residential proxies (bypasses Cloudflare) | Paid per 1k results | Weekly |
| **YouTube (no captions)** | Niche travel vlogger content | **`yt-dlp`** to download audio → **OpenAI Whisper** or **Deepgram** STT transcription | Paid per minute of audio | Weekly |
| **Instagram & TikTok** | Trending visual travel reels, captions, geotags | Aggregator platforms: **Octolens**, **Prowlo**, or unofficial Graph API scrapers | Paid subscription | Weekly |
| **X / Twitter** | Real-time disruptions (strikes, delays, closures, weather) | Official **X Basic/Pro API** | $100+/month | Real-time |

> **Transition milestone (v0 → v1):** Do not move to v1 until the v0 pipeline can consistently take a multi-day query (e.g., "4-day budget food tour of Hanoi"), filter out data from irrelevant cities, and output a logically sequenced itinerary without chronological errors. Once that logic is reliable, add the paid data layers.

### Extraction Mini-LLM Chain

Raw blog/forum text is unstructured. A lightweight extraction chain converts it to a canonical JSON schema before embedding:

```
Raw blog text (HTML → plain text)
         │
         ▼
  Gemini Flash (extraction prompt, temp=0.1, max_tokens=1200)
         │
         ▼
  Structured ItineraryCorpusDoc:
  {
    "destination": "Kyoto",
    "country": "Japan",
    "duration_days": 5,
    "pace": "moderate",         # inferred from density of activities
    "purpose": "cultural",      # inferred from themes
    "budget_tier": "mid-range", # inferred from accommodation/dining mentions
    "group_type": "couple",     # inferred from author context
    "source_url": "...",
    "source_name": "Nomadic Matt",
    "published_month": "November",
    "days": [
      {
        "day_number": 1,
        "theme": "Temples & Bamboo",
        "places": ["Fushimi Inari", "Arashiyama", "Philosopher's Path"],
        "tips": ["Go to Fushimi Inari before 8am", "Rent a bike in Arashiyama"]
      }
    ]
  }
```

**Extraction prompt key rules:**
- Extract only factual day-by-day structure — no opinions
- Infer pace from activity density (relaxed < 4/day, moderate 4–5, packed 5+)
- Infer budget tier from hotel names / dining style mentioned
- If structure is ambiguous (listicle without days), skip the document

### Embedding Strategy for Corpus

Each document gets **two embeddings** stored side by side:

| Embedding | Text embedded | Purpose |
|---|---|---|
| **Config embedding** | `"5 day moderate cultural couple trip Kyoto Japan November"` | Retrieved by user config similarity |
| **Content embedding** | Full day-by-day places text | Retrieved by semantic content similarity |

At retrieval time, query both and merge results (weighted: 60% config, 40% content).

### Qdrant Collection Schema

```python
# New collection: itinerary_corpus (384-dim)
PointStruct(
    id=hash(source_url),
    vector=embed(config_text),          # primary vector
    payload={
        "destination": "Kyoto",
        "country": "Japan",
        "duration_days": 5,
        "pace": "moderate",
        "purpose": "cultural",
        "budget_tier": "mid-range",     # "budget" | "mid-range" | "premium" | "luxury"
        "group_type": "couple",         # "solo" | "couple" | "family" | "friends" | "group"
        "published_month": "November",
        "source_name": "Nomadic Matt",
        "source_url": "https://...",
        "days_json": "[{...}]",         # structured days for injection
        "quality_score": 0.82,          # source authority weight
        "ingested_at": "2026-06-29",
    }
)
```

### Source Quality Scoring

Not all sources are equal. Weight retrieved documents by source authority:

| Source tier | Examples | Quality score |
|---|---|---|
| **Authoritative** | Lonely Planet, Nomadic Matt, Travel + Leisure | 0.90–1.00 |
| **Community (high karma)** | Reddit posts with score > 500 | 0.75–0.90 |
| **Community (standard)** | Reddit posts score 50–500, TripAdvisor threads | 0.55–0.75 |
| **Community (low signal)** | Reddit score < 50, generic blogs | 0.30–0.55 |
| **Generated (WanderPlanner)** | Past generated itineraries (Section 10) | 0.60–0.85 (feedback-based) |

### Ingestion Pipeline (Scheduled)

```
Scheduler (APScheduler — existing)
    │
    ├── Monthly: blog scrapers (Nomadic Matt, Planet D, Lonely Planet)
    │       └── scrape HTML → strip boilerplate → extraction LLM → validate JSON
    │           → embed (config + content) → upsert Qdrant [itinerary_corpus]
    │
    ├── Weekly: TripAdvisor forum scraper
    │       └── Filter threads: "day 1", "itinerary", "trip report"
    │
    └── Daily: Reddit trip reports + YouTube descriptions
            └── Reddit: r/travel + r/solotravel, flair=trip-report
                YouTube: search "X day itinerary [destination]" → extract description
```

### Injection into LLM Prompt

```python
async def retrieve_itinerary_examples(trip_config: TripConfig) -> str:
    config_text = (
        f"{trip_config.dates.duration_days or 7} day "
        f"{trip_config.pace} {trip_config.purpose} "
        f"{_group_type(trip_config.group)} trip "
        f"{trip_config.destination.city} {trip_config.destination.country}"
    )
    vector = embed([config_text])[0]
    hits = client.search(
        "itinerary_corpus", vector,
        query_filter=Filter(must=[
            FieldCondition("destination", MatchValue(trip_config.destination.city))
        ]),
        limit=3, score_threshold=0.72
    )
    examples = []
    for hit in hits:
        days = json.loads(hit.payload["days_json"])
        source = hit.payload["source_name"]
        examples.append(f"[Source: {source}]\n" + _format_days_brief(days))
    return "\n\n---\n\n".join(examples)
```

Added to the itinerary system prompt as `{examples}`:
```
REAL TRAVELLER ITINERARIES FOR REFERENCE (use as inspiration, not verbatim):
{examples}
```

**Token budget:** 3 itineraries × ~150 tokens each = ~450 tokens. Negligible cost, high grounding value.

---

## 10. Learning from Past Generated Itineraries (Persona-Based Retrieval)

### Concept: RAG as Collaborative Filtering

Every itinerary WanderPlanner generates is a data point. When a new user has a similar profile to past users, the system retrieves their itineraries as implicit "examples of what worked". This is **few-shot prompting with dynamically retrieved examples** — the model learns behaviorally without any retraining.

The key insight: a digital nomad solo traveller in Chiang Mai for 10 days at ₹80k budget is nearly identical to 20 previous such users. Their itinerary should start from that learned baseline, not from scratch.

### What to Store per Generated Itinerary

```python
# New collection: generated_itineraries (384-dim)
PointStruct(
    id=uuid(),
    vector=embed(persona_fingerprint),
    payload={
        # Config snapshot
        "destination": "Chiang Mai",
        "country": "Thailand",
        "duration_days": 10,
        "pace": "moderate",
        "purpose": "solo_backpacking",
        "budget_tier": "budget",        # derived from amount per person per day
        "personas": ["digital_nomad"],
        "themes": ["food", "culture"],
        "group_type": "solo",
        "travel_month": "February",

        # Generated output
        "itinerary_summary": "10 days in Chiang Mai: temples, nomad cafes, night markets...",
        "top_places": ["Doi Suthep", "Nimman Road", "Sunday Walking Street"],
        "days_json": "[{...}]",

        # Implicit quality signals (updated after session)
        "was_shared": False,
        "session_duration_s": 0,
        "regenerated": False,
        "regen_count": 0,
        "post_gen_chat_turns": 0,
        "quality_score": 0.70,          # baseline; updated by background task
        "generated_at": "2026-06-29",
    }
)
```

### Persona Fingerprint (Embedding Key)

```python
def _persona_fingerprint(trip_config: TripConfig) -> str:
    budget_tier = _budget_tier(trip_config.budget.amount, trip_config.group)
    group_type = _group_type(trip_config.group)
    month = trip_config.dates.start[:7] if trip_config.dates.start else "flexible"
    return (
        f"{trip_config.destination.city} {trip_config.destination.country} "
        f"{trip_config.dates.duration_days or 7}d "
        f"{trip_config.pace} {trip_config.purpose} "
        f"{budget_tier} {group_type} "
        f"{' '.join(trip_config.personas)} "
        f"{' '.join(trip_config.themes[:3])} "
        f"{month}"
    )
# Example: "Chiang Mai Thailand 10d moderate solo_backpacking budget solo digital_nomad food culture 2026-02"
```

### Implicit Quality Signal Scoring

No user ratings needed — infer quality from behaviour:

| Signal | Score delta | Logic |
|---|---|---|
| Not regenerated | +0.30 | User accepted first output |
| Session duration > 3 min | +0.25 | Read it thoroughly |
| Shared via link | +0.25 | Strong endorsement |
| Post-gen chat used (not regenerate) | +0.10 | Engaged with refinements |
| Regenerated once | −0.20 | Didn't like first output |
| Regenerated twice+ | −0.40 | Strong dissatisfaction |
| Session < 30s | −0.15 | Bounced without reading |

```python
def _compute_quality_score(signals: dict) -> float:
    score = 0.70  # baseline
    if not signals.get("regenerated"): score += 0.30
    if signals.get("session_duration_s", 0) > 180: score += 0.25
    if signals.get("was_shared"): score += 0.25
    if signals.get("post_gen_chat_turns", 0) > 0: score += 0.10
    score -= min(0.40, signals.get("regen_count", 0) * 0.20)
    if signals.get("session_duration_s", 999) < 30: score -= 0.15
    return max(0.0, min(1.0, round(score, 2)))
```

### Retrieval at Inference Time

```python
async def retrieve_similar_past_itineraries(trip_config: TripConfig) -> str:
    fingerprint = _persona_fingerprint(trip_config)
    vector = embed([fingerprint])[0]
    hits = client.search(
        "generated_itineraries", vector,
        query_filter=Filter(
            must=[FieldCondition("destination", MatchValue(trip_config.destination.city))],
            should=[
                FieldCondition("pace", MatchValue(trip_config.pace)),
                FieldCondition("group_type", MatchValue(_group_type(trip_config.group))),
            ]
        ),
        limit=10, score_threshold=0.78
    )
    # Re-rank: cosine similarity × quality_score
    ranked = sorted(hits, key=lambda h: h.score * h.payload.get("quality_score", 0.70), reverse=True)[:2]

    if not ranked:
        return ""

    examples = []
    for hit in ranked:
        p = hit.payload
        examples.append(
            f"[Past trip: {p['duration_days']}d {p['pace']} {p['purpose']} "
            f"for {p['group_type']}, {p['budget_tier']} budget, {p['travel_month']}]\n"
            f"Top places: {', '.join(p.get('top_places', []))}\n"
            f"Summary: {p['itinerary_summary']}"
        )
    return "\n\n".join(examples)
```

Injected as `{past_itineraries}`:
```
PAST ITINERARIES FOR SIMILAR TRAVELLERS (high-quality, accepted by users):
{past_itineraries}

Use these as inspiration for structure, place selection and pacing.
Do NOT copy verbatim — adapt to this user's specific dates and preferences.
```

### Cold Start Strategy

At zero users the `generated_itineraries` collection is empty. Bootstrap with:

1. **Pre-seed from itinerary_corpus**: copy 50 high-quality blog itineraries with `quality_score=0.75`
2. **Internal test runs**: generate itineraries for 20 popular destination × persona combos, `quality_score=0.70`
3. **After ~100 real users**: real signal dominates; pre-seeded content naturally de-ranks

### The Learning Flywheel

```
New user generates itinerary
        │
        ├── Stored in generated_itineraries (quality_score = 0.70 baseline)
        │
        ├── User behaviour tracked (shared? regenerated? session time?)
        │
        └── Background task updates quality_score after session ends
                │
                └── Next similar user retrieves this itinerary
                        │
                        ├── High quality_score → injected as example → better output
                        └── Low quality_score → filtered out → not used
```

Over time the system **automatically learns** which itinerary structures work for which personas at which destinations — without any model retraining, fine-tuning, or labelling.

---

## 11. Unified Metadata Schema for All Ingested Content

Every document from every source (wiki, reddit, blog, YouTube, TripAdvisor, etc.) is normalised to a **single JSON schema** before embedding. This makes retrieval filters consistent across collections:

```json
{
  "source":          "reddit",
  "source_name":     "r/solotravel",
  "url":             "https://reddit.com/r/solotravel/...",
  "destination":     "Kyoto",
  "country":         "Japan",
  "content":         "The bamboo forest is crowded, go to Gio-ji Temple instead...",
  "published_date":  "2026-03-15",
  "content_type":    "review",
  "attraction_type": "nature",
  "language":        "en",
  "quality_score":   0.72,
  "ingested_at":     "2026-06-29"
}
```

**`content_type`** options: `"review"`, `"itinerary"`, `"tip"`, `"guide"`, `"news"`, `"vlog_transcript"`  
**`attraction_type`** options: `"restaurant"`, `"museum"`, `"nature"`, `"transport"`, `"accommodation"`, `"activity"`, `"festival"`

The `attraction_type` field enables **precision filtering** in the LLM prompt — e.g. for a food-focused trip, filter `attraction_type IN ("restaurant", "food_market")` before retrieval, cutting irrelevant museum content entirely.

---

## 12. Agentic Router (v1 Feature)

For queries that require **real-time data** (not static blog posts), a router agent decides whether to hit the vector database or bypass it entirely:

```
User question: "Is the Louvre open right now?"
        │
        ▼
    Agentic Router (lightweight classifier)
        │
        ├── Static knowledge query → vector DB retrieval → LLM generation
        │   (e.g., "What are the best temples in Kyoto?")
        │
        └── Real-time query → bypass vector DB → live API call
            (e.g., "Is the Louvre open?", "Are there flight delays to Tokyo today?")
                    │
                    ├── Opening hours  → Google Places API / OSM
                    ├── Travel alerts  → X (Twitter) API / government advisories
                    └── Flight status  → Aviation APIs
```

```python
# Router implementation using Gemini Flash as classifier (< 50ms)
ROUTER_PROMPT = """
Classify this travel question as one of:
- "static": answered from travel guides, blogs, or general knowledge
- "realtime": requires current/live data (opening hours, delays, closures, prices today)

Question: {question}
Respond with ONLY the word "static" or "realtime".
"""

async def route_query(question: str) -> str:
    resp = await gemini_flash(ROUTER_PROMPT.format(question=question))
    return resp.strip().lower()  # "static" or "realtime"
```

**When to implement:** After v0 pipeline is stable and X/Twitter API is integrated (v1).

---

## 13. Full Updated RAG Architecture (v2)

```
═══════════════════════════════════════════════════════════════════
                INGESTION PIPELINES (offline / scheduled)
═══════════════════════════════════════════════════════════════════

  EXTERNAL CONTENT                                 QDRANT COLLECTIONS
  ─────────────────                                ──────────────────
  Wikivoyage         ──(on-demand scrape)──▶       [wiki]
  Reddit top posts   ──(every 6 hours)────▶        [reddit]
  OSM POIs           ──(weekly)───────────▶        [osm_pois]              ← ingestor needed
  Travel blogs       ──(monthly)──────────▶        [itinerary_corpus]      ← NEW
  Reddit trip rprt   ──(daily)────────────▶        [itinerary_corpus]      ← NEW
  YouTube vlogs      ──(daily)────────────▶        [itinerary_corpus]      ← NEW
  Visa/entry rules   ──(monthly static)───▶        [visa_info]             ← NEW
  WanderPlanner output  ──(per generation)───▶        [generated_itineraries] ← NEW
  Pre-generated      ──(bootstrap)────────▶        [itinerary_cache]       ← NEW

═══════════════════════════════════════════════════════════════════
                RETRIEVAL PIPELINE (per request, ~50ms)
═══════════════════════════════════════════════════════════════════

  User TripConfig
       │
       ├─ [1] Build queries
       │       ├── context query:    "{dest} travel {personas} highlights activities food"
       │       ├── config query:     "{N}d {pace} {purpose} {budget_tier} {group_type} {dest}"
       │       └── fingerprint:      full persona fingerprint string
       │
       ├─ [2] Parallel Qdrant searches (async)
       │       ├── wiki             (context query)     → top 5 chunks
       │       ├── reddit           (context query)     → top 5 chunks
       │       ├── osm_pois         (context query)     → top 5 POIs
       │       ├── itinerary_corpus (config query)      → top 3 real itineraries
       │       └── generated_itin.  (fingerprint)       → top 2 past WanderPlanner trips
       │
       ├─ [3] Rerank + deduplicate
       │       └── score × quality_score; remove jaccard > 0.6 duplicates
       │
       ├─ [4] Summarise to token budget
       │       ├── context chunks:    600 tokens
       │       ├── real itineraries:  450 tokens (3 × 150)
       │       └── past itineraries:  300 tokens (2 × 150)
       │                              ─────────────────────
       │                              Total: ~1,350 tokens  (vs 7,500 today)
       │
       └─ [5] Inject into LLM prompt
               ├── {context}           → wiki + reddit + OSM tips
               ├── {examples}          → blog/forum/YouTube itineraries
               └── {past_itineraries}  → WanderPlanner learned itineraries

═══════════════════════════════════════════════════════════════════
                POST-GENERATION PIPELINE
═══════════════════════════════════════════════════════════════════

  Itinerary generated
       │
       ├── Store in [generated_itineraries] (quality_score = 0.70)
       ├── Store in [itinerary_cache] (for API-down fallback)
       └── Background task: update quality_score after session ends
```

---

## 14. Updated Token Cost Comparison

| Context component | Today | v2 (optimised RAG) |
|---|---|---|
| Wiki/Reddit raw chunks | ~7,500 tokens | ~600 tokens (summarised) |
| Real itinerary examples | 0 | ~450 tokens |
| Past WanderPlanner itineraries | 0 | ~300 tokens |
| **Total context** | **~7,500 tokens** | **~1,350 tokens** |
| **Output quality** | Training data only | Real + learned + community-grounded |
| **Cost per session (Gemini 2.0 Flash)** | **~$0.007** | **~$0.004** |
| **At 10,000 sessions/month** | **~$70** | **~$40** |

More context signal, fewer tokens, better output.

---

## 15. Updated Implementation Roadmap

| Priority | Task | Effort | Status / Impact |
|---|---|---|---|
| P0 | Wire `retrieve_context()` into `_gemini_itinerary()` | 30 min | ✅ Done — grounds all production itineraries |
| P0 | Fix Reddit `_extract_destination()` NER | 2 hrs | ✅ Done — Reddit destination filter usable |
| P1 | Context summarisation (600-token budget) | 3 hrs | ✅ Done — 87% token reduction |
| P1 | Better chunking (500-char sentence boundaries) | 2 hrs | ✅ Done — higher retrieval precision |
| P1 | Async concurrency fix (`asyncio.to_thread` + batch embed) | 3 hrs | ✅ Done — throughput ~10 → ~23.6 req/s @ concurrency=50 |
| P1 | OSM POI ingestor (Overpass API) | 4 hrs | ✅ Done — `scrapers/osm.py`, weekly scheduler job |
| P1 | Hybrid BM25 + semantic search (`rank_bm25` library) | 4 hrs | ✅ Done — `services/search.py::_bm25_search_collection_sync` |
| P1 | HyDE query augmentation | 2 hrs | ✅ Done — template-based, `services/hyde.py` |
| P1 | `itinerary_cache` + fallback retrieval logic | 4 hrs | ✅ Done — `services/itinerary_cache.py`, 3-tier fallback |
| P1 | Cross-encoder reranker | 1 day | ✅ Done — scoped to itinerary generation only (§3J) |
| P1 | Golden dataset + automated retrieval eval | 4 hrs | ✅ Done — `eval/golden_dataset.json` + `eval/run_rag_eval.py` |
| P1 | `generated_itineraries` collection + store on generate | 4 hrs | ❌ Pending — learning flywheel not yet started |
| P2 | Travel blog scraper — `feedparser` + BeautifulSoup (Nomadic Matt, Planet D, Lonely Planet) | 1 day | ❌ Pending — itinerary_corpus seeded with authoritative content |
| P2 | Reddit PRAW ingester (replace direct JSON feed) — flair:trip-report filter, top 5 comments per post | 4 hrs | ❌ Pending — high-volume, properly tagged community itineraries |
| P2 | YouTube `youtube-transcript-api` scraper (no API key) | 4 hrs | ❌ Pending — video-native itinerary patterns, free |
| P2 | Unified metadata schema normalisation across all scrapers | 3 hrs | ❌ Pending — consistent filters; `attraction_type` precision retrieval |
| P2 | Quality score background task (session signals) | 4 hrs | ❌ Pending — enables persona-based re-ranking |
| P2 | Visa info collection | 3 hrs | ❌ Pending — entry requirements surfaced in wizard |
| P2 | Time-decay scoring in reranker | 2 hrs | ✅ Done — 18-month half-life, floor 40% |
| P2 | Semantic chunking (by section headers / Reddit comments) | 3 hrs | ✅ Done |
| P3 | Wikimedia API ingestion (replace Wikivoyage scraper) | 2 hrs | ❌ Pending — more stable than HTML scraping |
| P3 | TripAdvisor via Apify/Bright Data (v1 premium) | 2 days | ❌ Pending — current ratings and reviews |
| P3 | `yt-dlp` + Whisper STT for non-captioned YouTube videos (v1) | 1 day | ❌ Pending — niche travel vlogger content |
| P3 | Instagram/TikTok via Octolens or Prowlo (v1) | 2 days | ❌ Pending — trending visual content, geotag-based retrieval |
| P3 | X/Twitter real-time API for disruptions (v1) | 1 day | ❌ Pending — immediate travel alerts, strikes, closures |
| P3 | Agentic router (static vs real-time query classifier) | 1 day | ❌ Pending — routes live queries to fresh APIs, static to vector DB |
| P3 | Dual embedding per corpus doc (config + content) | 3 hrs | ❌ Pending — more precise retrieval |
| P3 | LLM-generated HyDE passages (upgrade from template-based) | 4 hrs | ❌ Pending — only worth it if template coverage proves insufficient |

---

*Maintainer: Engineering · Last updated: July 2, 2026 · Version 4.0*
