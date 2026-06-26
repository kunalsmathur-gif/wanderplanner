# WanderPlan — System Design Document

**Version:** 6.0 (LLM Anya Wizard · Mobile-Responsive · RAG Architecture Documented)  
**Last Updated:** June 26, 2026  
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

The wizard is now fully LLM-powered. Each user message is sent to `POST /api/wizard-chat` (Gemini 2.5 Flash, temp 0.6). Anya returns a conversational reply, optional chip suggestions, and a `config_patch` of newly extracted fields. The frontend merges patches into a local `partialConfig` state and shows progress pills for the 6 required fields.

```
openWizard() or openWizardWithPreload(preload)
         │
         ├─ If wizardPreload set (inspiration card or Start Anywhere):
         │    → pre-populate partialConfig with destination + duration_days
         │    → send bootstrap message: "I want to plan a trip to [dest] for [N] days."
         │    → clearWizardPreload()
         │
         ▼
LLMWizard.tsx → POST /api/wizard-chat
{
  messages: [{role, content}, ...],     ← full conversation history (last 20)
  partial_config: { ...merged config }, ← all fields collected so far
  preloaded_destination: "Bali, Indonesia | null"
}
         │
         ▼
wizard_chat_chain.py
  │
  ├─ Build system prompt with:
  │    - Anya personality + collection rules
  │    - collected_state summary (human-readable current partial_config)
  │    - preloaded_destination
  │
  ├─ Call Gemini 2.5 Flash (temp 0.6, max_tokens 1024)
  │
  └─ Response: { reply, chips, config_patch, ready_to_generate, summary }
         │
         ├─ Merge config_patch into partialConfig (frontend)
         │
         ├─ Update field progress pills (6 required fields)
         │
         ├─ ready_to_generate=false → show reply + chips → wait for next user message
         │
         └─ ready_to_generate=true (server-validated: all 6 fields present)
              → show TripSummary card with summary line
              → show "Generate my itinerary 🚀" button
              → User clicks generate:
                   → merge partialConfig into tripConfigStore
                   → streamItinerary(fullConfig, ...) → SSE → ThreeColumnLayout
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
         ├─ RAG RETRIEVAL ─────────────────────────────────────────────
         │    services/search.py → retrieve_context(trip_config)
         │    │
         │    ├─ Build query: "{city} {themes} travel tips highlights"
         │    │    e.g. "Bali beach culture travel tips highlights food"
         │    │
         │    ├─ embed(query) → 384-dim vector (all-MiniLM-L6-v2)
         │    │
         │    ├─ Qdrant cosine search (filtered by destination):
         │    │    reddit collection → top 10
         │    │    wiki   collection → top 10
         │    │
         │    └─ Return top-20 chunks sorted by cosine score
         │         e.g. "Ubud rice terraces: go at 7am to beat tourists"
         │              "Tanah Lot best at sunset, accessible at low tide"
         │
         ├─ Assemble Gemini prompt:
         │    SYSTEM_PROMPT.format(
         │      context = top-20 RAG chunks (Reddit + Wikivoyage),
         │      trip_config = TripConfig JSON
         │    )
         │
         └─ Retry loop (5 attempts):
              Model 1-3: gemini-2.5-flash (temp 0.4)
              Model 4:   gemini-2.5-flash-lite
              Model 5:   gemini-1.5-flash
              Each: validate JSON schema → ItineraryResponse
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
         share.py router
           → slug = uuid4().hex[:8]   e.g. "a1b2c3d4"
           → _store[slug] = payload
           → return { slug, url: "/t/a1b2c3d4" }
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
GET /api/share/a1b2c3d4
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
  messages: [{role:'user'|'assistant', content:string}],
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

#### `GET /api/share/{slug}` ⭐ NEW
```
Response: same shape as POST /api/share body, or 404
```

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

Two collections, both using `all-MiniLM-L6-v2` (384 dims, cosine distance):

### `reddit` collection
```json
{
  "vector": [384 floats],
  "payload": {
    "text": "Reddit post / comment text",
    "destination": "Bali",
    "subreddit": "solotravel",
    "score": 142,
    "url": "https://reddit.com/r/..."
  }
}
```

### `wiki` collection
```json
{
  "vector": [384 floats],
  "payload": {
    "text": "Wikivoyage section text",
    "destination": "Bali",
    "section": "Get around",
    "url": "https://en.wikivoyage.org/..."
  }
}
```

### Ingestion
- **Reddit**: Scraped via JSON API every 6h (APScheduler). Subreddits: `solotravel`, `travel`, `backpacking`, destination-specific.
- **Wiki**: Scraped from Wikivoyage on startup. Sections: Overview, Get in, Get around, See, Eat, Sleep, Stay safe.

---

## 10. Gemini Prompt Design & Temperature Settings

### Model & Temperature Reference

| Endpoint | Chain file | Model | Temperature | Max tokens |
|---|---|---|---|---|
| `POST /api/wizard-chat` | `wizard_chat_chain.py` | `gemini-2.5-flash` | **0.6** | 1024 |
| `POST /api/chat-refine` | `chat_refine_chain.py` | `gemini-2.5-flash` | **0.5** | 1024 |
| `POST /api/generate-itinerary` (attempts 1-3) | `itinerary_chain.py` | `gemini-2.5-flash` | **0.4** | 16384 |
| `POST /api/generate-itinerary` (attempt 4) | `itinerary_chain.py` | `gemini-2.5-flash-lite` | **0.4** | — |
| `POST /api/generate-itinerary` (attempt 5) | `itinerary_chain.py` | `gemini-1.5-flash` | **0.4** | — |
| `POST /api/extract-trip` | `extract_trip_chain.py` | `gemini-2.5-flash` | **0.1** | 512 |
| `POST /api/recommend-cities` | `recommend_cities_chain.py` | `gemini-2.5-flash` | **0.4** | 1024 |

Temperature rationale:
- **0.6** — Wizard: conversational warmth without hallucinating field values
- **0.5** — Chat refine: friendly but semi-deterministic for config patches
- **0.4** — Itinerary/cities: structured JSON; lower = fewer schema violations
- **0.1** — Extraction: near-deterministic; wrong extraction = wrong wizard preload

---

### System Prompt 1 — Anya Wizard (`wizard_chat_chain.py`)

```
You are Anya, WanderPlan's AI travel concierge — warm, enthusiastic, and concise.

REQUIRED FIELDS (collect all 6 before ready_to_generate=true):
1. purpose       2. destination   3. dates
4. budget.amount 5. group.adults  6. pace

SMART EXTRACTION:
- "just me and my wife"  → group: {adults: 2, ...}
- "₹1.5 lakh"           → budget: {amount: 150000, currency: "INR"}
- "a week"              → dates: {flexible: true, duration_days: 7}
- "suggest me"          → destination_mode: "exploring"

RESPONSE FORMAT (JSON every turn):
{
  "reply": "...", "chips": [...],
  "config_patch": { ...new fields only... },
  "ready_to_generate": false,
  "summary": null
}

CURRENT COLLECTED STATE: {collected_state}
PRELOADED DESTINATION: {preloaded_destination}
```

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
| `ALLOWED_ORIGINS` | `http://localhost:3000` | ✅ | CORS whitelist |
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
  → All fail → SSE error event { code, message, retryable: true }
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
