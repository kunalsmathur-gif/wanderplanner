# WanderPlan — System Design Document

**Version:** 8.1 (RAG v5.2 — Multi-query RRF · Time-decay · Paragraph chunking · Gemini RAG wired)  
**Last Updated:** June 29, 2026  
**Audience:** Engineering team and technical stakeholders

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Data Flow: LLM Anya Wizard](#2-data-flow-llm-anya-wizard)
3. [Data Flow: Start Anywhere](#3-data-flow-start-anywhere)
4. [Data Flow: Itinerary Generation with RAG](#4-data-flow-itinerary-generation-with-rag)
5. [Data Flow: Persistent Anya Chat](#5-data-flow-persistent-anya-chat)
6. [Data Flow: Share Trip Link](#6-data-flow-share-trip-link)
7. [Data Flow: Voice Interaction](#7-data-flow-voice-interaction)
8. [API Contract](#8-api-contract)
9. [Qdrant Collection Schema](#9-qdrant-collection-schema)
10. [Gemini Prompt Design & Temperature Settings](#10-gemini-prompt-design--temperature-settings)
11. [Frontend State Architecture](#11-frontend-state-architecture)
12. [Design System](#12-design-system)
13. [Environment Variables Reference](#13-environment-variables-reference)
14. [Performance & Cost Analysis](#14-performance--cost-analysis)
15. [Resilience & Retry Architecture](#15-resilience--retry-architecture)

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          BROWSER (Desktop)                               │
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  Next.js 16 (Turbopack) + TypeScript                             │   │
│  │  Design System: Space Grotesk + DM Sans + JetBrains Mono        │   │
│  │  Theme: Light / Dark (CSS custom properties, no-flash script)   │   │
│  │                                                                   │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │  LandingHero  (shown when no itinerary loaded)            │  │   │
│  │  │  - Hero headline + "Start planning with Anya" CTA         │  │   │
│  │  │  - Start Anywhere: URL/text input → extract-trip API      │  │   │
│  │  │  - Feature grid (4 cards)                                 │  │   │
│  │  │  - Inspiration gallery (12 cards, Wikipedia photos)       │  │   │
│  │  │  - FAQ section (JSON-LD SEO)                              │  │   │
│  │  │  - Nav anchors: Inspiration · FAQ                         │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  │                                                                   │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │  LLMWizard — Full-screen Overlay (LLM-powered)       │  │   │
│  │  │  🎙️ Voice Mode: SpeechRecognition + SpeechSynthesis  │  │   │
│  │  │  💬 Natural conversation with Gemini 2.5 Flash        │  │   │
│  │  │  🏷️ 6-field progress pills + chip quick-replies       │  │   │
│  │  │  🎯 WizardPreload: inspiration/URL click pre-fills    │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  │                                                                   │   │
│  │  ┌──────────┐  ┌──────────────────────────┐  ┌───────────────┐  │   │
│  │  │ Column 1 │  │       Column 2            │  │   Column 3    │  │   │
│  │  │  (20%)   │  │        (55%)              │  │    (25%)      │  │   │
│  │  │          │  │                           │  │               │  │   │
│  │  │ Metrics  │  │ [destination · ShareBtn]  │  │ Map (Leaflet) │  │   │
│  │  │ Expense  │  │ ItineraryTimeline         │  │ ⤢ Full screen │  │   │
│  │  │ Currency │  │  PolaroidCard activity    │  │ Best Time     │  │   │
│  │  │ Booking  │  │  cards (wiki photos)      │  │ Travel Tips   │  │   │
│  │  │   Hub    │  │ ComparisonPanel           │  │               │  │   │
│  │  └──────────┘  └──────────────────────────┘  └───────────────┘  │   │
│  │                                                                   │   │
│  │  Floating: Anya Orb → ChatPanel (post-gen persistent chat)      │   │
│  │                                                                   │   │
│  │  Zustand (6 stores):                                             │   │
│  │  appStore · tripConfigStore · wizardChatStore                    │   │
│  │  itineraryStore · chatStore · bookingStore                       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────────────┘
                              │ HTTPS / JSON / SSE
┌────────────────────────────▼────────────────────────────────────────────┐
│                    FastAPI (Python 3.9+) Port 8000                        │
│                                                                            │
│  POST /api/wizard-chat         → Anya LLM wizard (Gemini 2.5 Flash)  ⭐NEW  │
│  POST /api/generate-itinerary  → Gemini 2.5 Flash (5× retry + fallback) │
│  POST /api/chat-refine         → Anya post-gen chat handler              │
│  POST /api/recommend-cities    → City suggestions (Gemini)               │
│  POST /api/extract-trip        → URL/text → trip fields (Gemini) ⭐NEW  │
│  POST /api/share               → Serialize trip → slug          ⭐NEW   │
│  GET  /api/share/{slug}        → Read-only trip data            ⭐NEW   │
│  GET  /api/travel-tips         → Gemini tips (cached 1h)                 │
│  GET  /api/best-time/{city}    → Open-Meteo weather                      │
│  GET  /api/geocode             → Nominatim proxy (en, is_country) ⭐UPD │
│  POST /api/compare-destinations→ 10-param AI comparison                  │
│  GET  /health                  → Readiness probe                          │
│                                                                            │
│  Security middleware (⭐ NEW v10.0):                                      │
│  - slowapi rate limiting: 10/min on all LLM-backed endpoints, 30/min      │
│    default elsewhere (IP-keyed, in-memory — single-instance only)        │
│  - CORS: allow_credentials=False, wildcard origin rejected by validator  │
│  - Structured JSON logging with PII redaction (core/logging_config.py)  │
│  - Prompt-injection guard (core/prompt_guard.py) wraps/neutralizes all   │
│    untrusted text (chat, scraped pages, RAG context) before LLM prompts │
│  - SSRF-hardened URL fetch in extract-trip (private-IP/metadata block)  │
│                                                                            │
│  Background (APScheduler):                                                │
│  - Reddit content refresh every 6h                                        │
│  - Qdrant vector ingestion on startup                                     │
└───────┬───────────────┬──────────────────┬────────────────────────────────┘
        │               │                  │
┌───────▼─────┐  ┌──────▼──────┐  ┌───────▼──────────────────────────────┐
│   Qdrant    │  │   Gemini    │  │  External APIs                        │
│ (in-memory) │  │  2.5 Flash  │  │                                        │
│             │  │  (primary)  │  │  • Nominatim/OSM  — geocoding         │
│ Collections │  │  lite / 1.5 │  │  • Open-Meteo    — weather            │
│  - reddit   │  │  fallbacks  │  │  • Reddit JSON   — travel tips        │
│  - wiki     │  │             │  │  • YouTube       — video thumbnails   │
└─────────────┘  └─────────────┘  │  • Wikipedia API — destination photos │
                                   │    (frontend, free, no key, CORS-safe)│
                                   └───────────────────────────────────────┘

Embedding Model: sentence-transformers/all-MiniLM-L6-v2 (local, 384 dims)
```

---

## 2. Data Flow: LLM Anya Wizard

### 2.1 Overview

The wizard is fully LLM-powered. Each user message is sent to `POST /api/wizard-chat` (Gemini 2.5 Flash, temp 0.4). Anya returns a conversational reply, optional chip suggestions, and a `config_patch` of newly extracted fields. The frontend merges patches into a local `partialConfig` state, tracks `_checkpoint_asked`, and shows progress pills for the 6 required fields. Assistant turns are JSON-wrapped with the real `config_patch` when replayed to Gemini so the model learns from the actual extraction history, not plain-text replies alone.

```
openWizard() or openWizardWithPreload(preload)
         │
         ├─ If wizardPreload set → pre-populate partialConfig, send bootstrap message
         │
         ▼
STAGE 1 — Collect 6 required fields
LLMWizard.tsx → POST /api/wizard-chat
{
  messages: [{role, content, config_patch?}, ...],
  partial_config: { ...merged config + _checkpoint_asked flag },
  preloaded_destination: "Bali, Indonesia | null"
}
         │
         ▼
wizard_chat_chain.py
  ├─ System prompt v5: personality, Indian context, STT/Hinglish rules,
  │    6 required fields, 3-stage flow, config_patch rules, concrete MUST examples
  ├─ CURRENT_STATE summary injected (shows status: all-6-collected or checkpoint-asked)
  ├─ Assistant history replayed as JSON with real config_patch per turn
  ├─ Call Gemini 2.5 Flash (temp 0.4, max_tokens 800)
  ├─ Retry: 3 attempts with exponential backoff on 503/429/UNAVAILABLE
  ├─ Smart mock fallback reads partial_config and asks next missing field
  └─ Parse JSON: { reply, chips, config_patch, ready_to_generate, summary }
         │
         ├─ Stage 1: ready_to_generate=false, missing fields → ask next question
         │
         ├─ Stage 2: all 6 fields present → Anya asks "anything else?" checkpoint
         │    → Frontend sets _checkpoint_asked=true in partialConfig
         │    → Chips: "Just generate it!", "Add themes", "Add departure city"
         │
         └─ Stage 3: checkpoint done + user confirms → ready_to_generate=true
              → show "Generate my itinerary" button
              → User clicks → merge partialConfig → streamItinerary → SSE
```

### 2.2 Required Fields

| # | Field | Example value |
|---|---|---|
| 1 | `purpose` | `"honeymoon"` |
| 2 | `destination` or `destination_mode` | `{city:"Bali", country:"Indonesia"}` or `"exploring"` |
| 3 | `dates` | `{start:"2026-09-01", end:"2026-09-08"}` or `{flexible:true, duration_days:7}` |
| 4 | `budget.amount` | `80000` (INR) |
| 5 | `group.adults` | `2` |
| 6 | `pace` | `"moderate"` |

### 2.3 Smart Extraction Examples

| User says | config_patch emitted |
|---|---|
| `"just me and my wife"` | `{group: {adults: 2, kids: [], seniors: 0, infants: 0, pets: 0}}` |
| `"₹1.5 lakh total"` | `{budget: {amount: 150000, currency: "INR"}}` |
| `"7 nights in September"` | `{dates: {start: "2026-09-01", end: "2026-09-07", flexible: false}}` |
| `"suggest me a destination"` | `{destination_mode: "exploring"}` |
| `"exploring Rajasthan"` | `{destination_mode: "country", destination_country: "India"}` |
| `"yaar Bali trip 7 days mein karo, budget 1.5L types"` | `{destination: {city:"Bali",...}, dates: {flexible:true, duration_days:7}, budget: {amount:150000,...}}` |
| `"araam se travel karna hai"` | `{pace: "relaxed"}` |
| `"family ke saath 4 log"` | `{group: {adults: 4,...}}` |

---

## 3. Data Flow: Start Anywhere

```
User pastes URL or text into LandingHero input
         │
         ▼
handleStartAnywhere()
         │
         ├─ Empty input → openWizard() (plain)
         │
         └─ Has input → POST /api/extract-trip { input: string }
                │
                ▼
         Backend: extract_trip.py router
                │
                ├─ Starts with "http(s)://" ?
                │    └─ httpx.get(url) → strip HTML → first 6000 chars
                │
                └─ Extract trip text
                         │
                         ▼
                  Gemini 2.5 Flash (temp 0.1)
                  System: extraction schema
                  Output: ExtractedTrip JSON
                         │
                         ▼
              { destination, destination_country,
                duration_days, themes, budget_inr, summary }
                         │
         ◄───────────────┘
         │
         ├─ destination found →
         │    openWizardWithPreload({
         │      city: result.destination,
         │      country: result.destination_country,
         │      days: result.duration_days ?? 7,
         │      label: "City, Country"
         │    })
         │
         └─ no destination → openWizard() (plain fallback)
```

---

## 4. Data Flow: Itinerary Generation with RAG

```
User clicks "Generate my itinerary 🚀" (LLMWizard)
         │
         ▼
LLMWizard → merge partialConfig → tripConfigStore.updateConfig()
         │
         ▼
streamItinerary(fullConfig, ...)
         │
         ▼
POST /api/generate-itinerary { trip_config: TripConfig }
         │
         ▼
itinerary_chain.py
         │
         ├─ CACHE CHECK (best-effort, non-blocking on success path) ──────
         │    itinerary_cache.py stores on success; consulted only in the
         │    failure/fallback branch below (see §15)
         │
         ├─ RAG RETRIEVAL ──────────────────────────────────────────────
         │    services/search.py → retrieve_context(trip_config, enable_reranking=True)
         │    │
         │    ├─ Build 3 query variants in parallel:
         │    │    Q1: "{city} travel {personas} highlights activities food"
         │    │    Q2: "things to do in {city} {purpose} {pace} hidden gems"  ── run through HyDE
         │    │    Q3: "{city} best restaurants sightseeing transport safety"
         │    │
         │    ├─ HyDE (services/hyde.py): Q2 is replaced with a synthesized
         │    │    hypothetical travel-guide passage before embedding — template-based,
         │    │    persona/pace/purpose aware, no extra LLM call/latency
         │    │
         │    ├─ asyncio.gather() → 3 × semantic_search(limit=15), each wrapped in
         │    │    asyncio.to_thread() so calls run on real worker threads (previously
         │    │    all serialized on the event loop — fixed this session)
         │    │    Each: hybrid search = BM25 (Qdrant scroll, destination-scoped) +
         │    │    embed(query) → 384-dim cosine search, fused via RRF
         │    │    Filter: destination == trip_config.destination.city
         │    │    Collections: wiki + reddit (split 50/50 per query)
         │    │
         │    ├─ _rrf_merge(): Reciprocal Rank Fusion (k=60)
         │    │    Score = Σ 1/(60 + rank_i) across 3 query lists
         │    │    Top-40 unique chunks kept for reranking
         │    │
         │    └─ Cross-encoder reranking (ms-marco-MiniLM-L-6-v2) — ONLY on this
         │         call site (itinerary generation). Scores (query, doc) pairs jointly;
         │         falls back to RRF order on any failure. Top-20 returned with published_date.
         │         Disabled by default elsewhere (settings.reranking_enabled=False) since a
         │         cross-encoder pass adds real latency (~23.6 → ~7 req/s @ concurrency=50
         │         when enabled globally) — scoping it here keeps other RAG callers fast.
         │
         ├─ RAG COMPRESSION ────────────────────────────────────────────
         │    summarise_context(context_docs, max_chars=2400)
         │    │
         │    ├─ Time-decay: score × (0.4 + 0.6 × 0.5^(age/548))
         │    │    e.g. 3yr-old post: 0.91 → 0.50, 1-month post: 0.91 → 0.89
         │    │
         │    ├─ Score filter: drop decayed < 0.35
         │    │
         │    ├─ Jaccard dedup: >60% word overlap → keep highest scored
         │    │
         │    ├─ Sort by decayed score DESC
         │    │
         │    └─ Truncate at 2400 chars (~600 tokens)
         │         was: ~30,000 chars (7,500 tokens) — 12× reduction
         │
         ├─ Assemble Gemini prompt:
         │    SYSTEM_PROMPT.format(
         │      context = summarised RAG context (≤600 tokens),
         │      trip_config = TripConfig JSON
         │    )
         │
         ├─ Retry loop (5 attempts):
         │    Model 1-3: gemini-2.5-flash (temp 0.4)
         │    Model 4:   gemini-2.5-flash-lite
         │    Model 5:   gemini-1.5-flash
         │    Each: validate JSON schema → ItineraryResponse
         │
         ├─ On success → store_itinerary() caches result (best-effort, strips
         │    any "_"-prefixed fallback markers so degraded output can never be cached)
         │
         ├─ On exception (all retries + Groq/Ollama exhausted) → _fallback_itinerary()
         │    3-tier chain: cache hit → OSM-grounded skeleton → RAG-tipped mock (see §15)
         │
         ◄─ SSE stream: status events → final ItineraryResponse
         │
         ▼
itineraryStore.setDays(days, score, breakdown)
closeWizard() → render ThreeColumnLayout
```

---

## 5. Data Flow: Persistent Anya Chat

```
User clicks FloatingAnyaButton (shown when itinerary exists)
         │
         ▼
useChatStore.open() → ChatPanel renders (fixed bottom-right, 360px wide)
         │
         ▼
User types message + sends
         │
         ▼
POST /api/chat-refine {
  messages: [...history],
  trip_config: tripConfigStore.config
}
         │
         ▼
chat_refine_chain.py
         │
         ├─ Gemini 2.5 Flash
         │    System: "You are Anya... CURRENT TRIP CONFIG: {config_json}"
         │    User: conversation history
         │
         └─ Output: { reply, action_type, config_patch, major_change }
         │
         ◄─ response
         │
         ├─ action_type = 'none'
         │    → display reply in ChatPanel
         │
         ├─ action_type = 'patch_config'
         │    → updateConfig(config_patch) silently
         │    → display reply ("I've updated your budget to ₹1.5L!")
         │
         └─ action_type = 'regenerate' + major_change = true
              → show confirmation dialog in ChatPanel:
                   ┌─────────────────────────────────┐
                   │ ⚠️ This change will regenerate  │
                   │ [Yes, apply & reset] [Just noting]│
                   └─────────────────────────────────┘
              ├─ "Yes" → updateConfig + resetItinerary
              └─ "Just noting it" → dismiss, no action
```

---

## 6. Data Flow: Share Trip Link

```
User clicks ShareButton (center column header)
         │
         ├─ shareUrl already cached → copy to clipboard → show "Link copied!"
         │
         └─ First click:
                  │
                  ▼
         POST /api/share {
           itinerary: { days, alignment_score, expense_breakdown },
           trip_config: tripConfigStore.config,
           labels: wizardChatStore.collectedLabels,
           destination_label: "Bali, Indonesia"
         }
                  │
                  ▼
         share.py router (rate-limited 10/min per IP)
           → slug = secrets.token_urlsafe(16)   e.g. "bS6AneQqDEye_NRSjOFCpg" (128-bit, ⭐ UPD v10.0)
           → _store[slug] = payload
           → return { slug, url: "/t/bS6AneQqDEye_NRSjOFCpg" }
                  │
                  ◄──────
                  │
         navigator.clipboard.writeText(origin + url)
         setShareUrl(url)  ← cache for subsequent clicks
         Button: "Link copied!" (green, 3s)

Recipient opens https://wanderplan.app/t/a1b2c3d4
         │
         ▼
app/t/[slug]/page.tsx
         │
         ▼
GET /api/share/bS6AneQqDEye_NRSjOFCpg
         │
         ├─ Found → { itinerary, trip_config, labels, destination_label }
         │    → render read-only day-by-day view
         │    → "👁 View-only" badge
         │    → "Plan my own trip →" CTA
         │
         └─ Not found → error state ("This trip link has expired or doesn't exist.")

Note: In-memory store resets on server restart.
      Production: swap _store for Redis or a database.
```

---

## 7. Data Flow: Voice Interaction

```
User clicks voice icon in wizard header
         │
         ▼
setVoiceModeActive(true) → ListeningOrb animates
         │
         ▼
SpeechRecognition.start()
  lang: 'en-IN'
  continuous: false
  interimResults: true
         │
User speaks → transcription fills input field in real-time
         │
         ▼
SpeechRecognition 'result' event (isFinal=true)
         │
         ▼
handleSubmit(transcript) → normal wizard message flow
         │
         ▼
Latest bot reply → SpeechSynthesis.speak(utterance)
  voice: first 'en-IN' female voice found in getVoices()
  rate: 0.9, pitch: 1.1, volume: 1.0
```

---

## 8. API Contract

### Request / Response Schemas

#### `POST /api/wizard-chat` ⭐ NEW
```
Request:  {
  messages: [{role:'user'|'assistant', content:string, config_patch?: object}],
  partial_config: Partial<TripConfig>,
  preloaded_destination: string | null
}
Response: {
  reply: string,
  chips: string[],
  config_patch: Partial<TripConfig>,
  ready_to_generate: bool,
  summary: string | null
}
```

#### `POST /api/generate-itinerary`
```
Request:  { trip_config: TripConfig }
Response: SSE stream
  event: status  → { message: string, step: int, total: int }
  event: result  → ItineraryResponse
  event: error   → { code: string, message: string, retryable: bool }

ItineraryResponse:
  { days: ItineraryDay[], alignment_score: int, expense_breakdown: ExpenseBreakdown }

ItineraryDay:
  { day_number: int, date: string, theme: string,
    items: ItineraryItem[], transit_warnings: TransitWarning[] }

ItineraryItem:
  { id, time_start, time_end, title, local_name?, description,
    location: { lat, lon, address, place_name },
    tags, booking_url, youtube_video_id, alignment_score, warnings }
```

#### `POST /api/chat-refine`
```
Request:  { messages: [{role:'user'|'assistant', content:string}], trip_config: TripConfig }
Response: { reply: string, action_type: 'none'|'patch_config'|'regenerate',
            config_patch: Partial<TripConfig>|null, major_change: bool }
```

#### `POST /api/extract-trip` ⭐ NEW
```
Request:  { input: string }   // URL or free-form text
Response: { destination: string|null, destination_country: string|null,
            duration_days: int|null, themes: string[], budget_inr: int|null,
            summary: string }
```

#### `POST /api/share` ⭐ NEW
```
Request:  { itinerary: object, trip_config: object,
            labels: Record<string,string>, destination_label: string }
Response: { slug: string, url: string }
```
Rate-limited 10/min per IP. Slug is `secrets.token_urlsafe(16)` (128-bit, ⭐ UPD v10.0 — was `uuid4().hex[:8]`).

#### `GET /api/share/{slug}` ⭐ NEW
```
Response: same shape as POST /api/share body, or 404
```
Rate-limited 10/min per IP.

#### `GET /api/geocode?q={query}`
```
Response: { display_name: string, lat: float, lon: float,
            country_code: string, is_country: bool }
```
`is_country=true` when Nominatim resolves the query to a country-level boundary
(no city/town/village/municipality in address; only country).

#### `POST /api/recommend-cities`
```
Request:  { country: string, trip_config: TripConfig }
Response: { cities: [{ name, country, lat, lon, tagline }] }
```

#### `POST /api/compare-destinations`
```
Request:  { destinations: string[], trip_config: TripConfig }
Response: ComparisonResponse (10 params × N destinations)
Parameters: budget_fit, weather, visa_ease, family_fit, romance, food_scene,
            adventure, safety, unique_experiences, overall_score
```

#### `GET /api/travel-tips?destination={city}`
```
Response: { tips: TravelTip[], reddit_highlights: RedditHighlight[] }
Cached: 1 hour per destination
```

#### `GET /api/best-time/{city}`
```
Response: { best_months: string[], weather_summary: string, avoid_months: string[],
            events: [{name, month, description}] }
```

---

## 9. Qdrant Collection Schema

Four active collections, all using `all-MiniLM-L6-v2` (384 dims, cosine distance):

### `reddit` collection
```json
{
  "vector": [384 floats],
  "payload": {
    "text": "Title prefix + paragraph chunk (≥80 chars)",
    "title": "Original Reddit post title",
    "destination": "Bali",
    "subreddit": "solotravel",
    "reddit_score": 142,
    "published_date": "2026-05-12",
    "post_url": "https://reddit.com/r/...",
    "text_preview": "First 300 chars of chunk"
  }
}
```
**Chunking:** Each post → N paragraph chunks (`\n\n` split, ≥80 chars). Each chunk is prefixed with the post title for standalone retrieval context. Point ID: `md5(post_url + text[:50])`.

### `wiki` collection
```json
{
  "vector": [384 floats],
  "payload": {
    "text": "Sentence-boundary chunk (~500 chars)",
    "destination": "Bali",
    "section": "see",
    "source_url": "https://en.wikivoyage.org/..."
  }
}
```
**Chunking:** Each Wikivoyage section → N sentence-boundary chunks (~500 chars, ≥80 chars min). Point ID: `md5(url + section + text[:50])`.

### `osm_pois` collection ✅ Live (weekly ingestion)
```json
{
  "vector": [384 floats],
  "payload": {
    "text": "Short embeddable description, e.g. 'Tanah Lot Temple — temple in Bali'",
    "name": "Tanah Lot Temple",
    "type": "temple",
    "lat": -8.6212,
    "lon": 115.0868,
    "destination": "Bali",
    "tags": ["tourism=attraction", "historic=temple"]
  }
}
```
Populated by `scrapers/osm.py::ingest_osm_pois()` from the free Overpass API (no key required); geocodes the destination, queries a ~5km radius across ~14 POI tag categories, dedupes by name. Consumed today by the Tier-2 RAG-skeleton fallback (§15); direct itinerary-grounding is a planned next step (see `docs/rag-strategy.md` §6, use case #1).

### `itinerary_cache` collection ✅ Live (populated organically on successful generations)
```json
{
  "vector": [384 floats],
  "payload": {
    "destination": "Bali",
    "duration_days": 5,
    "pace": "moderate",
    "purpose": "leisure",
    "itinerary_json": "{...serialized ItineraryResponse...}",
    "generated_at": "2026-07-02T10:00:00Z"
  }
}
```
Key: `embed(f"{destination} {duration_days}d {pace} {purpose} trip")`. Written by `services/itinerary_cache.py::store_itinerary()` after every successful LLM generation (best-effort, never blocks the response; strips any `_`-prefixed fallback markers so degraded fallback output is never cached). Read by `get_cached_itinerary()` with `score_threshold=0.88` as Tier 1 of the fallback chain.

### Ingestion Schedule
- **Reddit**: APScheduler, every 6h. Subreddits: `travel`, `solotravel`, `digitalnomad`, `backpacking`.
- **Wiki**: On-demand, triggered at itinerary generation time for the destination if not cached.
- **OSM POIs**: APScheduler, weekly (`osm_refresh_days` setting). Iterates `KNOWN_DESTINATIONS` with a polite delay (`osm_ingest_delay_seconds`) between Overpass calls.
- **Itinerary cache**: Event-driven — written on every successful itinerary generation, no separate scheduled job.

---

## 10. Gemini Prompt Design & Temperature Settings

### Model & Temperature Reference

| Endpoint | Chain file | Model | Temperature | Max tokens |
|---|---|---|---|---|
| `POST /api/wizard-chat` | `wizard_chat_chain.py` | `gemini-2.5-flash` | **0.4** | 800 |
| `POST /api/chat-refine` | `chat_refine_chain.py` | `gemini-2.5-flash` | **0.5** | 1024 |
| `POST /api/generate-itinerary` (attempts 1-3) | `itinerary_chain.py` | `gemini-2.5-flash` | **0.4** | 16384 |
| `POST /api/generate-itinerary` (attempt 4) | `itinerary_chain.py` | `gemini-2.5-flash-lite` | **0.4** | — |
| `POST /api/generate-itinerary` (attempt 5) | `itinerary_chain.py` | `gemini-1.5-flash` | **0.4** | — |
| `POST /api/extract-trip` | `extract_trip_chain.py` | `gemini-2.5-flash` | **0.1** | 512 |
| `POST /api/recommend-cities` | `recommend_cities_chain.py` | `gemini-2.5-flash` | **0.4** | 1024 |

Temperature rationale:
- **0.4** — Wizard: more deterministic extraction while keeping Anya conversational
- **0.5** — Chat refine: friendly but semi-deterministic for config patches
- **0.4** — Itinerary/cities: structured JSON; lower = fewer schema violations
- **0.1** — Extraction: near-deterministic; wrong extraction = wrong wizard preload

---

### System Prompt 1 — Anya Wizard (`wizard_chat_chain.py`)

**Version:** v5 (June 2026) — end-to-end extraction fix, JSON history replay, stricter patch behavior

**Key sections:**
- **System Purpose** — Anya is defined as a human travel professional speaking to a customer, not a slot-filling agent. Explicitly states she never narrates internal logic.
- **Persona & Tone** — warm Indian travel expert friend; 2-3 sentences max; TTS-optimised
- **Absolute Speaking Rules (§1a)** — hard prohibition on field names, system terms (`config_patch`, `destination_mode`, `missing field`), and internal reasoning in `reply`. Includes three verbatim WRONG/RIGHT examples from real failure cases.
- **Indian Cultural Context** — currency parsing (25k→25000, 1L→100000), travel seasons (Oct-Nov Diwali, Apr-May school holidays), joint family norms, veg/Jain food sensitivity
- **Audio/STT Handling** — Hinglish glossary (araam se→relaxed, family ke saath→family, bas karo→generate), filler word stripping, number speech (seven days→7)
- **6 Required Fields** — each with JSON key, valid values, and explicit phrase mappings
- **Optional Fields** — auto-inferred themes (honeymoon→wellness, adventure purpose→adventure)
- **Slot Filling** — never re-ask collected fields; defaults for "surprise me" (leisure, 6 days, 1L, moderate)
- **3-Stage Flow** — Stage 1: collect 6 fields → Stage 2: "anything else?" checkpoint → Stage 3: generate signal
- **config_patch Rules** — "include every extracted field even if you think it is already known" and `config_patch` must never be empty when the user just supplied usable trip info
- **JSON-Wrapped History** — assistant turns are replayed as JSON objects like `{"reply":"...","config_patch":{...}}` so Gemini learns from the real extraction history
- **Retry Logic** — 3 attempts with exponential backoff on 503/429/UNAVAILABLE before fallback
- **Smart Mock Fallback** — reads `partial_config` and asks the next missing required field instead of returning a generic fallback
- **Filled-State Consistency** — frontend `allFilled` is unified with `_isFieldFilled`, matching the progress pill logic
- **Output Schema** — JSON only; `reply` is described as "what Anya says on a phone call — no field names, no system terms, no internal reasoning"

The backend `_has_all_required()` server-validates `ready_to_generate`. Stage 2 checkpoint is tracked via `_checkpoint_asked` flag in `partialConfig` and surfaced to the LLM via `CURRENT_STATE`. Assistant history also includes raw-JSON leak guards (`or raw` → `or ""`) plus double-wrapped JSON detection before replay. A `_strip_leaked_reasoning()` function remains the last-resort safety net.

---

### System Prompt 2 — Anya Post-Gen Chat (`chat_refine_chain.py`)

```
You are Anya, WanderPlan's friendly AI travel assistant.

CURRENT TRIP CONFIG: {trip_config_json}

RESPONSE FORMAT:
{
  "reply": "...",
  "action_type": "none" | "patch_config" | "regenerate",
  "config_patch": null or { ...changed fields... },
  "major_change": false
}

- patch_config: small changes (pace, themes, accommodation)
- regenerate: destination/dates/group/budget >20% → ask user to confirm
```

---

### System Prompt 3 — Itinerary Generation (`itinerary_chain.py`)

```
You are WanderPlan, an expert AI travel advisor.
Output ONLY valid JSON matching the schema.

RULES:
- 3-6 items/day  •  relaxed=3-4  •  moderate=4-5  •  packed=5-6
- If kids: exclude bars, nightclubs, extreme sports
- If digital_nomad: add 2h Work Block per day
- If sports_fitness: add Training Window per day
- Tag photogenic spots with "instaworthy"
- MULTI-HOP: distribute days across all stops proportionally

DESTINATION RESEARCH: {context}    ← RAG-retrieved Qdrant chunks
TRIP CONFIGURATION:   {trip_config}
```

---

### System Prompt 4 — Extract Trip (`extract_trip_chain.py`)

```
You are a travel data extraction assistant. Extract structured trip info.
Return ONLY valid JSON:
{
  "destination": "City or null",
  "destination_country": "Country or null",
  "duration_days": int or null,
  "themes": ["list"],
  "budget_inr": int or null,
  "summary": "One sentence."
}
```
Temperature: 0.1 (deterministic) · Max tokens: 512

---

## 11. Frontend State Architecture

### Store Dependency Graph

```
appStore
  └── wizardPreload → consumed by LLMWizard on open

tripConfigStore
  └── config → consumed by: LLMWizard (on generate), itinerary chain, chat-refine, shareTrip, ShareButton

wizardChatStore
  ├── messages → rendered by LLMWizard (legacy: ConversationalWizard)
  ├── currentField → legacy field tracking
  └── collectedLabels → passed to shareTrip

itineraryStore
  ├── days → consumed by: ThreeColumnLayout, ItineraryTimeline, MapWrapper, ShareButton
  ├── activeDay → drives day-tab selection, map center
  └── expenseBreakdown → ExpenseBreakupCard

chatStore
  ├── isOpen → ChatPanel visibility
  └── messages → ChatPanel message history

bookingStore (persisted)
  └── bookings → BookingHub display + localStorage
```

### Key State Transitions

```
Landing page (no itinerary):
  LandingHero shown
  FloatingAnyaButton: hidden
  ChatPanel: hidden

Wizard open (no itinerary):
  LandingHero blurred/dimmed
  LLMWizard overlay shown (LLM-powered Anya)
  FloatingAnyaButton: hidden

Itinerary exists, wizard closed:
  ThreeColumnLayout shown
  FloatingAnyaButton: visible → click → chatStore.open()
  ChatPanel: visible when chatStore.isOpen

Itinerary exists, wizard open (edit flow):
  ThreeColumnLayout blurred/dimmed
  LLMWizard overlay shown
  ChatPanel: hidden (wizard takes precedence)

Full-screen map (step3View = 'map-full'):
  ThreeColumnLayout renders full-height MapWrapper
  Day-tab toolbar replaces column headers
  "Close map" → step3View = 'itinerary'
```

---

## 12. Design System

### Color Tokens

| Token | Light | Dark | Usage |
|---|---|---|---|
| `--_primary` | `#0EA5E9` | `#38BDF8` | CTAs, links, active states |
| `--_accent` | `#EA580C` | `#FB923C` | Hero CTA button |
| `--_ocean` | `#0C4A6E` | `#0C4A6E` | Headings |
| `--_bg` | `#F8FAFC` | `#0B1120` | Page background |
| `--_card` | `#FFFFFF` | `#111827` | Card surfaces |
| `--_card-elevated` | `#F1F5F9` | `#1E293B` | Elevated cards |
| `--_fg` | `#0F172A` | `#F1F5F9` | Primary text |
| `--_muted-fg` | `#64748B` | `#94A3B8` | Secondary text |
| `--_border` | `#E2E8F0` | `#1E293B` | Borders, dividers |

### CSS Specificity Note
`.input` class in `globals.css` sets `padding: 0.625rem 0.875rem`.
To override inline padding (e.g. icon-padded inputs), use `style={{ paddingLeft: '...' }}` (inline style beats class).

### Scrollable Column Chain
For `overflow-y-auto` to activate on column children:
```
div.h-screen.flex.flex-col   →  div.flex-1.overflow-hidden
→  main.h-full  →  ThreeColumnLayout  →  aside.overflow-y-auto
```
Breaking any link in this chain prevents scrolling. `<main className="h-full">` is critical.

### Component Conventions
- Design tokens via `var(--_*)` CSS custom properties — never hardcode hex colors
- Dark mode: all components use tokens; no Tailwind `dark:` prefixes needed
- `cn()` or direct Tailwind classname concatenation with `[].join(' ')`
- Lucide icons for all UI iconography (consistent 13–18px sizes in UI chrome)

---

## 13. Environment Variables Reference

### Backend (`apps/api/.env`)

| Variable | Default | Required | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | — | ✅ | Google Gemini API key |
| `LLM_PROVIDER` | `gemini` | — | `gemini` or `mock` (for testing) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | — | Primary model ID |
| `QDRANT_URL` | `:memory:` | — | Qdrant instance URL |
| `ALLOWED_ORIGINS` | `["http://localhost:3000"]` | ✅ | CORS whitelist — **must be JSON-array format** (pydantic-settings list parsing), `"*"` is rejected by a validator (⭐ NEW v10.0) |
| `LOG_LEVEL` | `INFO` | — | Structured JSON logging level (⭐ NEW v10.0, `core/logging_config.py`) |
| `NOMINATIM_USER_AGENT` | `wanderplan/1.0` | — | Nominatim ToS compliance |
| `NOMINATIM_RATE_LIMIT` | `1` | — | Requests per second |

### Frontend (`apps/web/.env.local`)

| Variable | Default | Required | Description |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | ✅ | Backend base URL |
| `NEXT_PUBLIC_MAPTILER_KEY` | — | — | MapTiler key (optional, default OSM tiles work) |

---

## 14. Performance & Cost Analysis

### Latency Targets

| Operation | Target | Actual (p95) |
|---|---|---|
| Wizard chat turn (LLM Anya) | < 4s | ~2–3s |
| Geocode (Nominatim, cached) | < 200ms | ~50ms (cache hit) |
| City recommendations | < 3s | ~2s |
| Trip extraction (Start Anywhere) | < 5s | ~3s |
| Itinerary generation | < 45s | ~25–35s |
| Chat refine response | < 8s | ~4s |
| Travel tips (cached) | < 200ms | ~50ms (cache hit) |

### Monthly Cost (100 active users)

| Service | Cost |
|---|---|
| Gemini 2.5 Flash (itinerary + chat + tips + extraction) | ~₹15–30 |
| Nominatim, Open-Meteo, Reddit, OSM, Wikipedia | Free |
| Vercel (frontend) | Free tier |
| Railway (backend) | Free tier ($5 credit covers ~10M req) |
| **Total** | **~₹15–30/month** |

Per-user cost: ~₹0.15–0.30

### Caching Strategy

| Resource | Cache Type | TTL |
|---|---|---|
| Geocode results | LRU (Python, `lru_cache`) | Process lifetime |
| Travel tips | In-process dict | 1 hour per destination |
| Wikipedia images | Module-level Map (JS) | Session lifetime |
| YouTube thumbnails | Module-level Map (JS) | Session lifetime |
| Share slugs | In-memory dict (Python) | Server process lifetime |

---

## 15. Resilience & Retry Architecture

### Itinerary Generation Retry Chain

```
Attempt 1: gemini-2.5-flash, temperature=0.7
  → JSON parse failure or schema mismatch?
Attempt 2: gemini-2.5-flash, temperature=0.5 (slightly more deterministic)
  → Still failing?
Attempt 3: gemini-2.5-flash, temperature=0.3
  → Still failing?
Attempt 4: gemini-2.5-flash-lite (simpler, faster, cheaper)
  → Still failing?
Attempt 5: gemini-1.5-flash (stable fallback)
  → All fail → RAG-powered 3-tier fallback (✅ new this cycle, replaces the old
     bare SSE-error behaviour):
       Tier 1: itinerary_cache lookup (cosine ≥ 0.88) → instant cached itinerary
       Tier 2: rag_skeleton_itinerary() — real OSM POIs slotted into day structure,
                requires ≥3 POIs ingested for the destination, else falls through
       Tier 3: _mock_itinerary(tip_texts=...) — static mock enhanced with real
                retrieved wiki/reddit snippets spliced in as "Local tip: ..."
                (always succeeds — final safety net)
```

### Extract Trip Resilience

```
3 attempts with 1s back-off between each.
All fail → return ExtractedTrip with all nulls + summary "Could not extract..."
Frontend fallback: openWizard() (plain, no preload)
```

### Wikipedia Image Resilience

```
useWikiImage(city) fetch fails → cache.set(key, null) → return null
Component: shows gradient fallback permanently (no retry loop)
```

### Chat Refine Resilience

```
POST /api/chat-refine fails →
  updateLastAssistant("Sorry, I couldn't connect right now. Please try again.")
  setStatus('error', 'Connection failed')
  Error banner shown in ChatPanel header
```

---

## 16. Change Log

### v10.0 (July 2026) — Security Hardening

Addresses 9 of the 10 findings in `docs/scaling-tech-challenges.md` §1 (full detail + status table: `docs/scaling-tech-challenges.md` §1a). Auth (#1) explicitly deferred.

- **SSRF fix** (`chains/extract_trip_chain.py`): DNS-resolve + reject private/loopback/link-local/reserved/multicast IPs (blocks cloud metadata IP `169.254.169.254`); manual redirect walk (max 3 hops, re-validated); 2MB response cap; content-type allowlist.
- **Rate limiting** (`core/rate_limit.py`, slowapi, IP-keyed, in-memory): `10/min` on all LLM-backed endpoints, `30/min` default elsewhere.
- **Share link hardening** (`routers/share.py`): `secrets.token_urlsafe(16)` (128-bit) replaces `uuid4().hex[:8]` (32-bit); both endpoints rate-limited.
- **Sanitized errors** (`core/errors.py`): all router exception handlers now log full detail server-side and return a generic message + reference id instead of `str(exc)`.
- **Prompt-injection guarding** (`core/prompt_guard.py`): `neutralize()` + `wrap_untrusted()` applied to RAG context, extract-trip fetched/pasted text, chat messages, and trip-config JSON across all LLM chains; frontend `lib/url-safety.ts` blocks unsafe `booking_url` schemes.
- **CORS hardening**: `allow_credentials=False`; `core/config.py` validator rejects `"*"` in `ALLOWED_ORIGINS`; CI wildcard check added.
- **Structured logging + redaction** (`core/logging_config.py`): JSON logs, PII redaction filter (emails/API keys/phone numbers); all `print()` calls replaced with `logger.*`.
- **Dependency hygiene**: `google-genai` pinned to `1.2.0`; `pip-audit` added to CI (advisory); `.github/dependabot.yml` added.
- **AGENTS.md review process**: `.github/CODEOWNERS` + CI job warns on AGENTS.md/CLAUDE.md changes.
- **Regression testing**: full backend pytest (89 passed/6 skipped), frontend `tsc --noEmit` + vitest (36 passed), live smoke tests of every modified endpoint in mock mode — no regressions.

### v9.0 (July 2026)
- RAG retrieval upgraded to hybrid search: BM25 (destination-scoped Qdrant scroll) fused with semantic cosine search via Reciprocal Rank Fusion, applied to every `semantic_search()` call
- HyDE query augmentation added (template-based hypothetical passage, `services/hyde.py`) for the "vibe" query variant
- Cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`) added, deliberately scoped to only the two true itinerary-generation call sites (`retrieve_context(..., enable_reranking=True)`); disabled by default elsewhere due to latency cost (~23.6 → ~7 req/s @ concurrency=50 when enabled globally)
- OSM POI ingestion built (`scrapers/osm.py`, Overpass API, weekly scheduled job) — `osm_pois` collection now live
- `itinerary_cache` collection now live — itineraries cached organically on successful generation, read back via cosine similarity ≥ 0.88
- 3-tier RAG-powered fallback chain implemented in `chains/itinerary_chain.py` for LLM failures: cache hit → OSM-grounded skeleton (`services/rag_fallback.py`) → RAG-tipped enhanced mock
- Fixed a concurrency bug where blocking `embed()`/Qdrant calls inside `async def` functions serialized on the event loop despite `asyncio.gather()`; now offloaded via `asyncio.to_thread()`, plus batched embedding of the 3 query variants in one call — throughput ~10 → ~23.6 req/s @ concurrency=50 (pre-hybrid/HyDE/rerank)
- Golden dataset + automated retrieval evaluation added (`apps/api/eval/golden_dataset.json`, `apps/api/eval/run_rag_eval.py`) — Precision@k/Recall@k/MRR/nDCG@k metrics
- Load testing tool added (`apps/api/load_test_rag.py`) to measure retrieval throughput/latency under concurrency

### v8.0 (June 2026)
- Wizard end-to-end fix: JSON history wrapping, retry logic, config_patch on ChatMessage, allFilled/isFieldFilled unification, smart mock fallback, prompt v5

### v7.0 (June 2026)
- Updated Anya wizard design to document prompt v4, persona-first approach, absolute speaking rules (§1a), and removal of `thought_process`
- Removed `thought_process` from `POST /api/wizard-chat` API contract; response is now `{ reply, chips, config_patch, ready_to_generate, summary }`
- Documented smarter extraction examples plus resilience fixes around bootstrap seeding, JSON fence parsing, stale closure protection, generate-loop handling, Gemini fallback behavior, and improved frontend error UX
