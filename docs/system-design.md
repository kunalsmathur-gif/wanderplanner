# WanderPlan — System Design Document

**Version:** 5.0 (Competitor Parity: Persistent Chat · Share · Start Anywhere · Booking Hub)  
**Last Updated:** June 26, 2026  
**Audience:** Engineering team and technical stakeholders

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Data Flow: Conversational Wizard](#2-data-flow-conversational-wizard)
3. [Data Flow: Start Anywhere](#3-data-flow-start-anywhere)
4. [Data Flow: Itinerary Generation](#4-data-flow-itinerary-generation)
5. [Data Flow: Persistent Anya Chat](#5-data-flow-persistent-anya-chat)
6. [Data Flow: Share Trip Link](#6-data-flow-share-trip-link)
7. [Data Flow: Voice Interaction](#7-data-flow-voice-interaction)
8. [API Contract](#8-api-contract)
9. [Qdrant Collection Schema](#9-qdrant-collection-schema)
10. [Gemini Prompt Design](#10-gemini-prompt-design)
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
│  │  │  ConversationalWizard — Full-screen Overlay               │  │   │
│  │  │  🎙️ Voice Mode: SpeechRecognition + SpeechSynthesis      │  │   │
│  │  │  💬 11-field chat flow (purpose → refinement)             │  │   │
│  │  │  🌍 Country auto-detection → multi-city selection         │  │   │
│  │  │  🎯 WizardPreload: inspiration/URL click pre-fills        │  │   │
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

## 2. Data Flow: Conversational Wizard

### 2.1 Wizard Field Flow

```
openWizard() or openWizardWithPreload(preload)
         │
         ├─ If wizardPreload set (from inspiration card or Start Anywhere):
         │    → pre-set destination + duration_days in tripConfigStore
         │    → add collectedLabels for destination + duration
         │    → Anya greets: "I see you're interested in [dest] for [N] days!"
         │    → clearWizardPreload()
         │    → start from 'purpose' (destination already set)
         │
         ├─ If existing itinerary: showEditEntry screen
         │    ├─ "Add custom instructions" → jump to refinement step
         │    └─ "Plan a new trip from scratch" → reset + start at step 1
         │
         ▼
Field Sequence (in wizardChatStore):
 1. purpose       → "What's the main purpose of your trip?"
                    Chips: Leisure, Adventure, Honeymoon, Family, Business, Solo, Group
 2. origin        → "Where are you starting from?"
                    Input: City name → GET /api/geocode → {city, lat, lon}
 3. destination_mode → "Do you have a specific destination in mind?"
                       Chips: "Yes, I have one" | "Suggest me!" | "Exploring a country"
         │
         ├─→ [Fixed] → user types city
         │    └─ GET /api/geocode → resolvePlace()
         │         ├─ is_country=true? → auto-switch to 'country' mode → multi-city flow
         │         └─ is_country=false? → setDestination, pushNextField('duration')
         │
         ├─→ [Exploring] → POST /api/recommend-cities (vibe text → cities)
         │    └─ DestinationCardGrid (Wikipedia photos) → user picks → next
         │
         └─→ [Country] → user types country → POST /api/recommend-cities
              └─ city chips → user picks 1+ cities (multi-city-confirm loop)
         │
 4. duration      → "How many days?" → updateDates({ duration_days })
 5. dates         → "When are you planning to travel?"
                    Chips: presets + Custom + Flexible
 6. group         → adults (counter) → kids count → kid ages (text input)
 7. budget        → amount input + currency selector
 8. accommodation → style chips (Hotel, Airbnb, Hostel, Resort...)
 9. pace          → Relaxed / Moderate / Packed
10. themes        → multi-select chips (Culture, Food, Adventure, Nature...)
11. refinement    → free-text textarea for custom instructions
12. summary       → TripSummaryCard → "Generate Itinerary 🚀"
```

### 2.2 State Updated Per Field

| Field | Store | Method |
|---|---|---|
| purpose | tripConfigStore | `updateConfig({ purpose })` |
| origin | tripConfigStore | `setOrigin({ city, lat, lon })` |
| destination_mode | tripConfigStore | `updateConfig({ destination_mode })` |
| destination | tripConfigStore | `setDestination({ city, country, lat, lon })` |
| hops (multi-city) | tripConfigStore | `addHop(hop)` |
| duration | tripConfigStore | `updateDates({ duration_days })` |
| dates | tripConfigStore | `updateDates({ start, end, flexible })` |
| group | tripConfigStore | `updateGroup({ adults, kids, seniors })` |
| budget | tripConfigStore | `updateBudget({ amount, currency })` |
| accommodation | tripConfigStore | `updateAccommodation({ style, ... })` |
| pace | tripConfigStore | `updateConfig({ pace })` |
| themes | tripConfigStore | `updateConfig({ themes })` |
| all labels | wizardChatStore | `addLabel(key, value)` |

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

## 4. Data Flow: Itinerary Generation

```
User clicks "Generate Itinerary 🚀"
         │
         ▼
ConversationalWizard → setPhase('generating')
         │
         ▼
POST /api/generate-itinerary { trip_config: TripConfig }
         │
         ▼
itinerary_chain.py
         │
         ├─ Build context: Qdrant semantic search (reddit + wiki docs)
         │    query: "{destination} {themes} travel tips"
         │    top-k: 5 reddit + 5 wiki docs
         │
         ├─ Assemble Gemini prompt:
         │    system: itinerary generation rules
         │    user: trip_config JSON + retrieved context
         │
         └─ Retry loop (5 attempts):
              Attempt 1–3: gemini-2.5-flash (temp 0.7)
              Attempt 4:   gemini-2.5-flash-lite
              Attempt 5:   gemini-1.5-flash
              Each: validate JSON schema → ItineraryResponse
         │
         ◄─ SSE stream: status events → final ItineraryResponse
         │
         ▼
itineraryStore.setDays(days, score, breakdown)
setPhase('done') → render ThreeColumnLayout
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

## 10. Gemini Prompt Design

### Itinerary Generation (System Prompt excerpt)
```
You are WanderPlan's expert travel planner. Generate a detailed day-by-day
itinerary in valid JSON matching the ItineraryResponse schema.

Rules:
- Activities must have realistic time_start/time_end (24h format)
- Budget allocation: activities ~40%, accommodation ~35%, food ~15%, transport ~10%
- Include local_name for Asian/Arabic destinations
- youtube_video_id: search term only (not a real video ID)
- alignment_score 0-100: how well this activity matches user's themes
- Add transit_warnings for same-day city changes > 2h apart
```

### Chat Refine (System Prompt excerpt)
```
You are Anya, WanderPlan's friendly AI travel assistant.
CURRENT TRIP CONFIG: {trip_config_json}

Return ONLY this JSON:
{
  "reply": "markdown response",
  "action_type": "none | patch_config | regenerate",
  "config_patch": { ... } | null,
  "major_change": boolean
}

Use patch_config for minor changes (budget, dates, pace).
Use regenerate for major changes (new destination, complete rethink).
```

### Extract Trip (System Prompt)
```
You are a travel data extraction assistant. Given text from any source,
extract structured trip info. Return ONLY valid JSON:
{
  "destination": "City name or null",
  "destination_country": "Country or null",
  "duration_days": integer or null,
  "themes": ["list of themes"],
  "budget_inr": integer or null,
  "summary": "One sentence description."
}
Temperature: 0.1 (deterministic extraction)
```

---

## 11. Frontend State Architecture

### Store Dependency Graph

```
appStore
  └── wizardPreload → consumed by ConversationalWizard on open

tripConfigStore
  └── config → consumed by: wizard, itinerary chain, chat-refine, shareTrip, ShareButton

wizardChatStore
  ├── messages → rendered by ConversationalWizard
  ├── currentField → drives wizard field flow
  └── collectedLabels → shown in TripSummaryCard, passed to shareTrip

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
  ConversationalWizard overlay shown
  FloatingAnyaButton: hidden

Itinerary exists, wizard closed:
  ThreeColumnLayout shown
  FloatingAnyaButton: visible → click → chatStore.open()
  ChatPanel: visible when chatStore.isOpen

Itinerary exists, wizard open (edit flow):
  ThreeColumnLayout blurred/dimmed
  ConversationalWizard overlay shown
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
