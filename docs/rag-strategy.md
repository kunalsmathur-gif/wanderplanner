# WanderPlan — RAG Strategy: Current State, Gaps & Roadmap
**Version:** 2.0 · **Date:** June 2026

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

### 3D — Hybrid Search: BM25 + Semantic (New)

Pure vector search struggles with **specific nouns** — "Tokyo" vs "Kyoto" may have similar embeddings but must be treated as hard filters. The fix is layering keyword matching on top of semantic search:

```python
# Hybrid retrieval: BM25 handles specific terms, semantic handles "vibe"
from rank_bm25 import BM25Okapi

async def hybrid_search(query: str, destination: str, corpus: list[dict], limit: int = 10) -> list[dict]:
    # Step 1: Hard metadata filter — only this destination (prevents Lyon appearing in Paris results)
    dest_docs = [d for d in corpus if d["destination"].lower() == destination.lower()]

    # Step 2: BM25 keyword pass (handles "anime", "sushi", specific place names)
    tokenized = [d["text"].lower().split() for d in dest_docs]
    bm25 = BM25Okapi(tokenized)
    bm25_scores = bm25.get_scores(query.lower().split())

    # Step 3: Semantic pass (handles "vibe" — "relaxed coffee culture", "instagrammable spots")
    semantic_hits = client.search("wiki", embed([query])[0],
        query_filter=Filter(must=[FieldCondition("destination", MatchValue(destination))]),
        limit=limit * 3)
    semantic_scores = {h.id: h.score for h in semantic_hits}

    # Step 4: Reciprocal Rank Fusion (RRF) — merge both rankings
    combined = _rrf_merge(bm25_scores, semantic_scores, dest_docs)
    return combined[:limit]
```

Use hybrid search for **all retrieval calls** (wiki, reddit, itinerary_corpus). Pure semantic search is kept only for the persona fingerprint lookup in `generated_itineraries`.

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

### 3G — Query Augmentation (HyDE)

Instead of one query, generate a hypothetical answer and embed that:
```python
# Before searching, generate a "hypothetical ideal context" and embed it
hypothetical = f"Top things to do in {dest} for a {purpose} trip: [ideal paragraph]"
# Embed this → closer to actual travel content than raw query embedding
```
This significantly improves recall for specific personas (digital nomad, family, etc.).

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

### 3I — Ingest OSM POIs

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
| **Generated (WanderPlan)** | Past generated itineraries (Section 10) | 0.60–0.85 (feedback-based) |

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

Every itinerary WanderPlan generates is a data point. When a new user has a similar profile to past users, the system retrieves their itineraries as implicit "examples of what worked". This is **few-shot prompting with dynamically retrieved examples** — the model learns behaviorally without any retraining.

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
  WanderPlan output  ──(per generation)───▶        [generated_itineraries] ← NEW
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
       │       └── generated_itin.  (fingerprint)       → top 2 past WanderPlan trips
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
               └── {past_itineraries}  → WanderPlan learned itineraries

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
| Past WanderPlan itineraries | 0 | ~300 tokens |
| **Total context** | **~7,500 tokens** | **~1,350 tokens** |
| **Output quality** | Training data only | Real + learned + community-grounded |
| **Cost per session (Gemini 2.0 Flash)** | **~$0.007** | **~$0.004** |
| **At 10,000 sessions/month** | **~$70** | **~$40** |

More context signal, fewer tokens, better output.

---

## 15. Updated Implementation Roadmap

| Priority | Task | Effort | Impact |
|---|---|---|---|
| P0 | Wire `retrieve_context()` into `_gemini_itinerary()` | 30 min | Grounds all production itineraries immediately |
| P0 | Fix Reddit `_extract_destination()` NER | 2 hrs | Makes Reddit destination filter usable |
| P1 | Context summarisation (600-token budget) | 3 hrs | 87% token reduction |
| P1 | Better chunking (500-char sentence boundaries) | 2 hrs | Higher retrieval precision |
| P1 | OSM POI ingestor (Overpass API) | 4 hrs | Real coordinates; no hallucinated lat/lon |
| P1 | `generated_itineraries` collection + store on generate | 4 hrs | Learning flywheel starts accumulating data immediately |
| P2 | Travel blog scraper — `feedparser` + BeautifulSoup (Nomadic Matt, Planet D, Lonely Planet) | 1 day | itinerary_corpus seeded with authoritative content |
| P2 | Reddit PRAW ingester (replace direct JSON feed) — flair:trip-report filter, top 5 comments per post | 4 hrs | High-volume, properly tagged community itineraries |
| P2 | YouTube `youtube-transcript-api` scraper (no API key) | 4 hrs | Video-native itinerary patterns, free |
| P2 | Unified metadata schema normalisation across all scrapers | 3 hrs | Consistent filters; `attraction_type` precision retrieval |
| P2 | Quality score background task (session signals) | 4 hrs | Enables persona-based re-ranking |
| P2 | `itinerary_cache` + fallback retrieval logic | 4 hrs | API-down resilience using real cached itineraries |
| P2 | Visa info collection | 3 hrs | Entry requirements surfaced in wizard |
| P2 | Time-decay scoring in reranker | 2 hrs | Filters out stale 2019 content automatically |
| P2 | Semantic chunking (by section headers / Reddit comments) | 3 hrs | Higher chunk precision, removes mid-sentence splits |
| P2 | Hybrid BM25 + semantic search (`rank_bm25` library) | 4 hrs | Specific nouns (Tokyo vs Kyoto) handled correctly |
| P3 | Wikimedia API ingestion (replace Wikivoyage scraper) | 2 hrs | More stable than HTML scraping |
| P3 | TripAdvisor via Apify/Bright Data (v1 premium) | 2 days | Current ratings and reviews |
| P3 | `yt-dlp` + Whisper STT for non-captioned YouTube videos (v1) | 1 day | Niche travel vlogger content |
| P3 | Instagram/TikTok via Octolens or Prowlo (v1) | 2 days | Trending visual content, geotag-based retrieval |
| P3 | X/Twitter real-time API for disruptions (v1) | 1 day | Immediate travel alerts, strikes, closures |
| P3 | Agentic router (static vs real-time query classifier) | 1 day | Routes live queries to fresh APIs, static to vector DB |
| P3 | HyDE query augmentation | 2 hrs | Better recall for niche personas |
| P3 | Dual embedding per corpus doc (config + content) | 3 hrs | More precise retrieval |
| P3 | Cohere Rerank / BGE-Reranker cross-encoder | 1 day | Highest precision; score top-50, return top-10 |

---

*Maintainer: Engineering · Last updated: June 2026 · Version 2.0*
