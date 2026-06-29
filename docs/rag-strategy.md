# WanderPlan — RAG Strategy: Current State, Gaps & Roadmap
**Version:** 1.0 · **Date:** June 2026

---

## 1. Are We Using RAG Today?

**Yes — but partially, with a critical gap.**

WanderPlan has a RAG infrastructure in place (Qdrant + `all-MiniLM-L6-v2` embeddings), but it is only wired into the **non-production** itinerary path (Groq/Ollama). The production path — **Gemini** — calls `_gemini_itinerary()` which **never calls `retrieve_context()`**. The RAG pipeline exists but is silently bypassed for every real user.

### What's Wired Up (Current)

```
Data Sources                Qdrant Collections           Where Used
─────────────────────       ──────────────────           ──────────────────────
Wikivoyage (on-demand) ──▶  wiki (384-dim)  ─────────▶  retrieve_context()
Reddit (every 6 hours) ──▶  reddit (384-dim) ─────────▶  /api/reddit-highlights
OSM POIs               ──▶  osm_pois (384-dim)            ⚠️ EMPTY — no ingestor exists
```

### What Is NOT Using RAG (Gaps)

| Component | RAG used? | Impact |
|---|---|---|
| Gemini itinerary generation | ❌ No | LLM generates from training data only — stale, hallucinated POIs |
| Anya wizard chat | ❌ No | Can't suggest real places; relies entirely on Gemini's parametric memory |
| City recommender | ❌ No | Suggestions not grounded in real community data |
| Destination comparison | ❌ No | Qualitative data is LLM-generated, not sourced from real posts |
| Best time (seasonal data) | ⚠️ Partial | Scrapes Wikivoyage live on every request — not cached in Qdrant |
| Reddit tagging | ⚠️ Broken | `_extract_destination()` always returns `"general"` — all posts untagged |

---

## 2. How Is It Leveraged Today?

### Itinerary Generation (Groq/Ollama path only)
```python
# services/search.py
async def retrieve_context(trip_config) -> list[dict]:
    query = f"{dest} travel {persona_keywords} highlights activities food"
    results = await semantic_search(query, dest, limit=20)
    # Returns top-20 chunks from wiki + reddit collections

# itinerary_chain.py (Groq path)
context_docs = await retrieve_context(trip_config)
context_text = "\n\n".join(doc["text"] for doc in context_docs[:20])
# Injected as {context} in SYSTEM_PROMPT
```
The 20 chunks (up to ~1500 chars each = up to 30,000 chars / ~7,500 tokens) are blindly concatenated and dropped into the prompt. No reranking, no summarisation.

### Reddit Highlights (UI component)
```python
# routers/reddit_highlights.py
vector = embed([f"{destination} travel tips guide best places"])[0]
hits = client.search(collection_name="reddit", query_vector=vector, limit=10)
```
Used for the Reddit highlights card in the itinerary UI. Works, but returns untagged posts (destination filter is unreliable due to the broken `_extract_destination()`).

### What's Missing from the Current Pipeline
1. **No reranking** — top-k by cosine score is naive; unrelated chunks score high if they share surface words
2. **No chunking strategy** — 1,500-char hard-cut mid-sentence
3. **No deduplication** — repeated context (e.g. 3 Wikivoyage chunks all saying "Bali is hot") wastes tokens
4. **No query augmentation** — single query per retrieval; misses semantic variants
5. **Context blindly injected** — no summarisation; a 30k-char dump hurts generation quality and costs ~$0.002 extra per call

---

## 3. Making RAG More Robust & Optimising LLM Token Usage

### 3A — Fix the Gemini Path (Critical)

```python
# itinerary_chain.py — _gemini_itinerary() must call retrieve_context
async def _gemini_itinerary(trip_config: TripConfig) -> dict:
    context_docs = await retrieve_context(trip_config)          # ADD THIS
    context_text = _summarise_context(context_docs, max_tokens=600)  # ADD THIS
    # ... rest of Gemini call with context_text injected
```

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

### 3D — Query Augmentation (HyDE)

Instead of one query, generate a hypothetical answer and embed that:
```python
# Before searching, generate a "hypothetical ideal context" and embed it
hypothetical = f"Top things to do in {dest} for a {purpose} trip: [ideal paragraph]"
# Embed this → closer to actual travel content than raw query embedding
```
This significantly improves recall for specific personas (digital nomad, family, etc.).

### 3E — Fix Reddit Destination Tagging

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

### 3F — Ingest OSM POIs

The `osm_pois` collection exists but is empty. Ingesting POI data (lat/lon, name, type, tags) would let the RAG system provide real coordinates to the itinerary LLM — eliminating hallucinated or wrong lat/lon values.

---

## 4. RAG as Fallback for Real-Time API Failures

### Current Fallback Behaviour
When Gemini fails after 3 retries:
- Wizard → smart mock (asks next missing field — context-aware but static)
- Itinerary → `_mock_itinerary()` returns 3 hardcoded days for "Destination City"

### RAG-Powered Fallback Strategy

#### Tier 1: Cached LLM Response (< 5ms)
Pre-generate and store itineraries for the 50 most popular destinations in Qdrant:
```python
# New collection: itinerary_cache (384-dim)
# Payload: {destination, duration_days, pace, purpose, itinerary_json, generated_at}
# Key: embed(f"{dest} {duration}d {pace} {purpose}")

async def get_cached_itinerary(trip_config) -> dict | None:
    query = f"{dest} {duration}d {pace} {purpose}"
    hits = client.search("itinerary_cache", embed([query])[0], score_threshold=0.88)
    if hits:
        return hits[0].payload["itinerary_json"]  # return cached; log cache hit
    return None
```

#### Tier 2: RAG-assembled itinerary skeleton (no LLM needed)
If cache misses and LLM is down:
```python
async def rag_skeleton_itinerary(trip_config) -> dict:
    """
    Build a minimal valid itinerary purely from Qdrant data:
    1. Retrieve top POIs for destination from osm_pois
    2. Retrieve "eat" section from wikivoyage
    3. Slot into day structure by pace (3-4 / 4-5 / 5-6 items per day)
    4. Return valid ItineraryResponse — no LLM call needed
    """
```

#### Tier 3: Smart mock with RAG context
Enhance `_mock_itinerary()` to read from Qdrant instead of returning hardcoded data:
```python
def _mock_itinerary(trip_config) -> dict:
    # Sync call to Qdrant — retrieve POI names for destination
    # Build day structure using real place names from OSM/Wikivoyage
    # Far better than "City Center Market at 09:00"
```

### Failure → Fallback Decision Tree

```
Gemini API call
    │
    ├─ Success ──────────────────────────────────────▶  Return itinerary
    │
    ├─ 503/429 (3 retries with backoff)
    │       │
    │       └─ Still failing
    │               │
    │               ├─ Check itinerary_cache (Qdrant)  ──▶  Cache hit → return cached
    │               │
    │               ├─ Cache miss → RAG skeleton from osm_pois + wikivoyage
    │               │
    │               └─ Qdrant also down → enhanced mock with hardcoded top-50 destinations
```

---

## 5. Recommended RAG Pipeline Architecture

```
INGESTION PIPELINE (offline / scheduled)
─────────────────────────────────────────
Wikivoyage ──▶ Scrape sections ──▶ Chunk (500 chars) ──▶ Embed ──▶ Qdrant [wiki]
Reddit     ──▶ Top posts (6hr)  ──▶ NER tag dest      ──▶ Embed ──▶ Qdrant [reddit]
OSM POIs   ──▶ Overpass API     ──▶ {name,type,coords} ──▶ Embed ──▶ Qdrant [osm_pois]
Itinerary  ──▶ Post-generation  ──▶ Cache popular trips ──▶ Embed ──▶ Qdrant [itinerary_cache]
Visa/Entry ──▶ Static JSON      ──▶ Per country rules   ──▶ Embed ──▶ Qdrant [visa_info]


RETRIEVAL PIPELINE (per request)
──────────────────────────────────
User trip config
    │
    ├─ Query augmentation (HyDE or multi-query)
    │       │
    │       ▼
    ├─ Parallel search: wiki + reddit + osm_pois
    │       │
    │       ▼
    ├─ Rerank (cross-encoder or MMR for diversity)
    │       │
    │       ▼
    ├─ Deduplicate (jaccard similarity)
    │       │
    │       ▼
    ├─ Summarise → 600-token context budget
    │       │
    │       ▼
    └─ Inject into LLM prompt {context}
```

---

## 6. Use Cases RAG Can Power in WanderPlan

| # | Use Case | Collections | Value |
|---|---|---|---|
| 1 | **Itinerary grounding** | wiki + osm_pois | Real POI names, correct lat/lon, no hallucinated venues |
| 2 | **Wizard destination chips** | wiki + osm_pois | When user says "Sri Lanka", Anya suggests Colombo/Galle/Kandy with reasons from real content |
| 3 | **Real-time traveller sentiment** | reddit | "Heads up — recent Reddit posts flag tourist scams near this area" |
| 4 | **Budget estimates from community data** | reddit | "r/solotravel users report ₹2,500/day in Bali for mid-range" |
| 5 | **Seasonal/festival injection** | wiki + events | Automatically add Diwali festival context if dates overlap |
| 6 | **Itinerary fallback (API down)** | itinerary_cache + osm_pois | Valid day plan without LLM call |
| 7 | **Visa & entry rules** | visa_info | "Indians need visa on arrival for Thailand — ₹2,500 approx" |
| 8 | **Safety advisories** | reddit + wiki | Flag destinations with recent negative posts (score-weighted) |
| 9 | **Food & dietary context** | wiki + reddit | Inject veg-friendly restaurant names for users who selected "Pure veg food" |
| 10 | **Post-gen chat refinements** | itinerary_cache | Anya answers "what's near Day 2's temple?" from RAG, not LLM parametric memory |

---

## 7. Token Cost Impact

| Scenario | Without RAG optimisation | With optimised RAG | Savings |
|---|---|---|---|
| Itinerary prompt context | ~7,500 tokens (20 raw chunks) | ~600 tokens (summarised) | ~87% reduction |
| Wizard (with destination grounding) | 0 tokens (no RAG) | ~200 tokens (top-3 POIs) | New capability |
| Per session total (Gemini 2.0 Flash) | ~$0.007 | ~$0.003 | ~57% |
| At 10,000 sessions/month | ~$70 | ~$30 | ~$40/mo |

---

## 8. Implementation Priority

| Priority | Task | Effort | Impact |
|---|---|---|---|
| P0 | Wire `retrieve_context()` into `_gemini_itinerary()` | 30 min | Immediately grounds all production itineraries |
| P0 | Fix Reddit `_extract_destination()` with keyword list | 2 hrs | Makes Reddit filter usable |
| P1 | Context summarisation before injection | 3 hrs | 87% token reduction |
| P1 | Better chunking (500-char, sentence-boundary) | 2 hrs | Higher retrieval precision |
| P1 | OSM POI ingestor (Overpass API) | 4 hrs | Real coordinates; no hallucinated lat/lon |
| P2 | `itinerary_cache` collection + cache hit logic | 4 hrs | Fallback + free repeat visits |
| P2 | Visa info collection + wizard injection | 3 hrs | Practical user value |
| P2 | HyDE query augmentation | 2 hrs | Better recall for niche trips |
| P3 | Cross-encoder reranker | 1 day | Best precision; overkill for Phase 1 |

---

*Maintainer: Engineering · Last updated: June 2026*
