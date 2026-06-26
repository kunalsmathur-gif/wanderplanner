# WanderPlan — Technical Documentation

**Version:** 6.0 (LLM Anya Wizard · Anya Prompt v3 · STT/Hinglish · 3-Stage Flow)  
**Last Updated:** June 26, 2026  
**Status:** Production-ready MVP

---

## Table of Contents

1. [Overview](#1-overview)
2. [Tech Stack](#2-tech-stack)
3. [Design System](#3-design-system)
4. [Frontend Architecture](#4-frontend-architecture)
5. [State Management (Zustand)](#5-state-management-zustand)
6. [Backend Architecture](#6-backend-architecture)
7. [API Reference](#7-api-reference)
8. [AI Models, Prompts & RAG](#8-ai-models-prompts--rag)
9. [Key Frontend Components](#9-key-frontend-components)
10. [Hooks & Utilities](#10-hooks--utilities)
11. [Voice Features](#11-voice-features)
12. [Data Flows](#12-data-flows)
13. [Environment Setup](#13-environment-setup)
14. [Recent Changes (v5.0 & v6.0)](#14-recent-changes-v50--v60)

---

## 1. Overview

WanderPlan is an AI-powered travel planning platform. Users interact with **Anya**, a conversational AI concierge, to produce a complete day-by-day itinerary. Key differentiators vs competitors (Mindtrip, TripIt, Travaa):

| Dimension | WanderPlan |
|---|---|
| Input method | Conversational wizard + voice + URL paste (Start Anywhere) |
| Post-gen experience | Persistent Anya chat panel for real-time refinements |
| Social sharing | Shareable read-only `/t/[slug]` trip link |
| Booking tracking | Integrated booking hub with localStorage persistence |
| Inspiration | Wikipedia-photo gallery with one-click wizard preload |
| Destination discovery | Country input auto-triggers multi-city selection |

---

## 2. Tech Stack

### Frontend (`apps/web`)

| Technology | Version | Purpose |
|---|---|---|
| **Next.js** | 16.x | App Router, Turbopack, RSC |
| **TypeScript** | 5.x | Type-safe development |
| **Tailwind CSS** | 4.x | Utility-first, CSS custom property tokens |
| **Zustand** | 5.x | State management (6 stores) |
| **React Leaflet** | 4.x | Interactive maps (OpenStreetMap tiles) |
| **Axios** | 1.x | HTTP client |
| **Web Speech API** | Native | Voice input (speech-to-text) |
| **Speech Synthesis API** | Native | Voice output (text-to-speech) |
| **Wikipedia REST API** | Free | Destination photos (no key, CORS-safe) |

### Backend (`apps/api`)

| Technology | Version | Purpose |
|---|---|---|
| **Python** | 3.9+ | Core language |
| **FastAPI** | 0.111+ | Async REST API |
| **Uvicorn** | - | ASGI server |
| **Pydantic** | 2.x | Data validation |
| **Google Generative AI** | Latest | Gemini API client |
| **Qdrant** | 1.x | Vector DB (in-memory mode) |
| **sentence-transformers** | - | Embeddings (all-MiniLM-L6-v2, 384 dims) |
| **httpx** | - | Async HTTP (URL fetch for Start Anywhere) |
| **BeautifulSoup4** | - | HTML parsing |
| **APScheduler** | - | Background jobs |

---

## 3. Design System

### Brand Mark
Geometric gold **W** with diamond intersection nodes at `(27,27)` and `(41,27)`, inner peak at `(34,8)`, compass arrow at `(62,6)`. SVG viewBox `0 0 72 58`. Sizes: `sm (28×35)`, `md (36×45)`, `lg (48×60)`.

### Color Tokens (`globals.css`)

```css
/* Light mode */
--_primary:        #0EA5E9   /* Sky blue — CTAs, links */
--_accent:         #EA580C   /* Adventure orange — hero CTA */
--_ocean:          #0C4A6E   /* Ocean navy — headings */
--_bg:             #F8FAFC
--_card:           #FFFFFF
--_card-elevated:  #F1F5F9
--_fg:             #0F172A
--_muted-fg:       #64748B
--_border:         #E2E8F0

/* Dark mode */
--_primary:        #38BDF8
--_accent:         #FB923C
--_bg:             #0B1120
--_card:           #111827
--_card-elevated:  #1E293B
--_fg:             #F1F5F9
--_muted-fg:       #94A3B8
--_border:         #1E293B
```

### Typography
- **Space Grotesk** — display, headers, logo wordmark
- **DM Sans** — body, labels, helper text
- **JetBrains Mono** — data values, amounts, codes

### Theme Toggle
`ThemeToggle.tsx` uses a `MutationObserver` on `document.documentElement` to avoid stale React closure bugs. Persistence key: `wp-theme`. Blocking `<head>` script prevents flash on load.

---

## 4. Frontend Architecture

### File Structure

```
apps/web/
├── app/
│   ├── layout.tsx          — Root layout, font loading, theme script
│   ├── page.tsx            — Root page: LandingHero or ThreeColumnLayout + overlays
│   └── t/[slug]/page.tsx   — Shareable read-only trip view
├── components/
│   ├── chat/
│   │   ├── ChatPanel.tsx   — Persistent Anya chat slide-in panel
│   │   ├── ChatMessage.tsx — Individual message bubble
│   │   └── ChatBubble.tsx
│   ├── common/
│   │   ├── LandingHero.tsx     — Landing: nav + hero + Start Anywhere + gallery + FAQ
│   │   ├── FloatingAnyaButton.tsx — Orb: opens ChatPanel (itinerary) or wizard (landing)
│   │   ├── ShareButton.tsx     — Generates /t/[slug] link, copies to clipboard
│   │   ├── WanderplanLogo.tsx  — SVG geometric gold W
│   │   └── ThemeToggle.tsx     — Dark/light toggle
│   ├── dashboard/
│   │   ├── Column1Metrics.tsx  — Left sidebar: metrics, expenses, currency, booking hub
│   │   ├── BookingHub.tsx      — Collapsible booking tracker (F7)
│   │   ├── CurrencyWidget.tsx
│   │   └── ExpenseBreakupCard.tsx
│   ├── itinerary/
│   │   ├── ItineraryTimeline.tsx — Day-tab activity list using PolaroidCard
│   │   ├── PolaroidCard.tsx      — Activity card: wiki photo + hover zoom + YouTube
│   │   ├── Column3Sidebar.tsx    — Map + best time + travel tips
│   │   └── BookingLinksSection.tsx
│   ├── layout/
│   │   └── ThreeColumnLayout.tsx — Responsive: 3-col on desktop, bottom-tab on mobile
│   └── wizard/
│       ├── LLMWizard.tsx         — LLM-powered Anya wizard (replaces state machine)
│       └── ConversationalWizard.tsx — Legacy scripted wizard (kept for reference)
├── hooks/
│   └── useWikiImage.ts     — Shared Wikipedia photo hook (cached, CORS-safe)
├── store/                  — See Section 5
├── lib/
│   └── api.ts              — All backend API calls (typed)
└── types/
    └── index.ts            — TripConfig, ItineraryDay, ItineraryItem, etc.
```

### Page Layout (`page.tsx`)

```
<div h-screen flex flex-col>
  ├── [Content area] — blurred/dimmed when wizard open
  │    ├── <LandingHero />          when no itinerary
  │    └── <ThreeColumnLayout />    when itinerary exists
  │
  ├── <FloatingAnyaButton />        when itinerary exists + wizard closed
  ├── <ChatPanel />                 when itinerary exists (hidden until opened)
  └── <LLMWizard />             when wizardOpen (fixed overlay, LLM-powered)
```

---

## 5. State Management (Zustand)

Six stores, all in `apps/web/store/`:

### `appStore.ts`
Controls wizard open state, preload, and step3View.

```typescript
{
  wizardOpen: boolean
  step3View: 'itinerary' | 'comparison' | 'map-full'
  wizardPreload: WizardPreload | null  // pre-fills destination+days from inspiration click

  openWizard(): void
  openWizardWithPreload(p: WizardPreload): void   // sets preload + opens wizard
  clearWizardPreload(): void
  closeWizard(): void
  setStep3View(view): void
}

interface WizardPreload {
  city: string        // e.g. "Bali"
  country: string     // e.g. "Indonesia"
  days: number        // e.g. 7
  label: string       // e.g. "Bali, Indonesia"
}
```

### `tripConfigStore.ts`
Holds the full `TripConfig` during wizard collection.

```typescript
{
  config: TripConfig   // purpose, dates, origin, destination, group, budget, themes...
  updateConfig(partial): void
  setDestination(dest | null): void
  addHop(hop): void    // multi-city stops (max 5)
  resetConfig(): void
  effectivePace(): 'relaxed' | 'moderate' | 'packed'  // auto-relaxed if kids < 5
}
```

`destination_mode`:
- `'fixed'` — single city typed by user
- `'exploring'` — AI suggests cities based on vibe
- `'country'` — user picks a country → multi-city selection flow

### `wizardChatStore.ts`
Chat message history + current wizard phase.

```typescript
{
  messages: WizardMessage[]            // bot/user bubbles
  currentField: WizardField            // which input is active
  phase: 'chatting' | 'summary' | 'generating' | 'done'
  collectedLabels: Record<string, string>  // display labels per field
}
```

### `itineraryStore.ts`
Holds generated itinerary data.

```typescript
{
  days: ItineraryDay[]
  alignmentScore: number
  expenseBreakdown: ExpenseBreakdown | null
  status: 'idle' | 'loading' | 'success' | 'error'
  activeDay: number
  setDays(days, score, breakdown?): void
  setActiveDay(i): void
  reset(): void
}
```

### `chatStore.ts`
Persistent post-generation Anya chat.

```typescript
{
  isOpen: boolean
  messages: ChatMessage[]     // {id, role: 'user'|'assistant', content, timestamp}
  status: 'idle' | 'sending' | 'error'
  open() / close() / toggle()
  addMessage(msg): ChatMessage
  updateLastAssistant(content): void
  clearHistory(): void
}
```

### `bookingStore.ts`
Booking hub with `zustand/persist` (localStorage key: `wanderplan-bookings`).

```typescript
{
  bookings: Booking[]         // {id, type, name, confirmation, date, amount, notes}
  addBooking(b): void
  removeBooking(id): void
  updateBooking(id, patch): void
}
type BookingType = 'Flight' | 'Hotel' | 'Activity' | 'Transport'
```

---

## 6. Backend Architecture

### File Structure

```
apps/api/
├── main.py                   — FastAPI app, CORS, router registration
├── core/
│   ├── config.py             — Settings (env vars)
│   ├── qdrant.py             — Qdrant client singleton + collection bootstrap
│   └── embeddings.py         — sentence-transformers model singleton + embed()
├── chains/
│   ├── itinerary_chain.py    — Gemini 2.5 Flash itinerary gen (5× retry + fallback)
│   ├── chat_refine_chain.py  — Anya post-gen chat (patch_config / regenerate actions)
│   ├── wizard_chat_chain.py  — Anya LLM wizard (collects TripConfig conversationally)
│   ├── extract_trip_chain.py — URL/text → structured trip fields (Start Anywhere)
│   └── ...
├── routers/
│   ├── itinerary.py          — POST /api/generate-itinerary (SSE streaming)
│   ├── chat_refine.py        — POST /api/chat-refine
│   ├── wizard_chat.py        — POST /api/wizard-chat
│   ├── extract_trip.py       — POST /api/extract-trip
│   ├── share.py              — POST /api/share + GET /api/share/{slug}
│   ├── geocode.py            — GET /api/geocode (Nominatim proxy)
│   ├── recommend_cities.py   — POST /api/recommend-cities
│   ├── comparison.py         — POST /api/compare-destinations
│   ├── travel_tips.py        — GET /api/travel-tips
│   ├── best_time.py          — GET /api/best-time/{city}
│   └── ...
├── services/
│   ├── search.py             — semantic_search() + retrieve_context() (Qdrant RAG)
│   └── geocode.py            — Nominatim proxy (1 req/s rate limit, LRU cache, is_country)
├── scrapers/
│   ├── reddit.py             — Reddit JSON scraper → Qdrant ingestion
│   └── wikivoyage.py         — Wikivoyage HTML scraper → Qdrant ingestion
└── models/
    └── common.py             — GeocodeResponse (+ is_country: bool)
```

### Country Detection (Geocode Service)

The geocode service now returns `is_country: bool` by checking whether Nominatim's address has no city/town/village/municipality — only a country name. The wizard uses this to automatically switch from `fixed` to `country` mode and show multi-city chip selection.

```python
is_country = (
    not address.get("city")
    and not address.get("town")
    and not address.get("village")
    and not address.get("municipality")
    and bool(address.get("country"))
)
```

---

## 7. API Reference

### `POST /api/wizard-chat` ⭐ NEW (v5.0)
LLM-powered Anya wizard. Collects TripConfig fields through natural conversation.

**Request:**
```json
{
  "messages": [{ "role": "user|assistant", "content": "..." }],
  "partial_config": { ...current TripConfig fields collected so far... },
  "preloaded_destination": "Bali, Indonesia | null"
}
```
**Response:**
```json
{
  "reply": "Friendly markdown response from Anya",
  "chips": ["Leisure", "Adventure"],
  "config_patch": { "purpose": "leisure" },
  "ready_to_generate": false,
  "summary": "7 days in Bali - Rs 80,000 - 2 adults - Moderate pace",
  "thought_process": "User just gave purpose. Still need destination, dates, budget, group, pace."
}
```

`ready_to_generate` is `true` only when all 6 required fields are present (server-side validated). `summary` is populated when ready.

### `POST /api/generate-itinerary`
Streaming SSE. Generates day-by-day itinerary from `TripConfig`.

**Request:** `{ trip_config: TripConfig }`  
**Response:** Server-Sent Events → final `ItineraryResponse`

### `POST /api/chat-refine`
Persistent Anya chat handler (used by `ChatPanel`).

**Request:** `{ messages: [{role, content}], trip_config: TripConfig }`  
**Response:**
```json
{
  "reply": "string",
  "action_type": "none | patch_config | regenerate",
  "config_patch": "Partial<TripConfig> | null",
  "major_change": "boolean"
}
```

### `POST /api/extract-trip` ⭐ NEW
Extracts structured trip fields from a URL or free-form text (blog, Reddit, notes).

**Request:** `{ input: "https://... or free text" }`

If `input` starts with `http://` or `https://`, the service fetches the URL content (first 6000 chars) before sending to Gemini.

**Response:**
```json
{
  "destination": "Bali | null",
  "destination_country": "Indonesia | null",
  "duration_days": 7,
  "themes": ["Beach", "Culture"],
  "budget_inr": 80000,
  "summary": "One sentence description"
}
```

### `POST /api/share` ⭐ NEW
Serializes itinerary + config to an in-memory store, returns a shareable slug.

**Request:**
```json
{
  "itinerary": { "days": [...], "alignment_score": 87 },
  "trip_config": { ... },
  "labels": { "destination": "Bali, Indonesia", "duration": "7 days" },
  "destination_label": "Bali, Indonesia"
}
```
**Response:** `{ "slug": "a1b2c3d4", "url": "/t/a1b2c3d4" }`

### `GET /api/share/{slug}` ⭐ NEW
Returns stored trip data for a slug. Returns 404 if not found.

**Response:** Same shape as the original `POST /api/share` body.

### `GET /api/geocode?q={query}`
Nominatim proxy with English name resolution, 1 req/s rate limiting, LRU cache.

**Response:**
```json
{
  "display_name": "Bali, Indonesia",
  "lat": -8.4095,
  "lon": 115.1889,
  "country_code": "id",
  "is_country": false
}
```

### `POST /api/recommend-cities`
**Request:** `{ country: "France", trip_config: TripConfig }`  
**Response:** `{ cities: [{ name, country, lat, lon, tagline }] }`

### `POST /api/compare-destinations`
**Request:** `{ destinations: string[], trip_config: TripConfig }`  
**Response:** `ComparisonResponse` (10 parameters per destination)

### `GET /api/travel-tips?destination={city}`
Returns Gemini-generated tips + Reddit highlights. Cached 1 hour.

### `GET /api/best-time/{city}`
Open-Meteo historical weather + season metadata.

### `GET /health`
`{ "status": "ready", "version": "1.0.0" }`

---

## 8. AI Models, Prompts & RAG

### Primary Model: Gemini 2.5 Flash

**Model ID:** `gemini-2.5-flash` (configurable via `GEMINI_MODEL` env var)

All LLM tasks use Gemini 2.5 Flash with task-specific temperature settings:

| Task | Temperature | Max Tokens | Notes |
|---|---|---|---|
| Itinerary generation (attempt 1) | 0.4 | 16384 | High-quality structured output |
| Itinerary generation (attempt 2) | 0.4 | 16384 | Retry — same settings |
| Itinerary generation (attempt 3) | 0.4 | 16384 | Retry — same settings |
| Itinerary generation (attempt 4) | 0.4 | — | Fallback: `gemini-2.5-flash-lite` |
| Itinerary generation (attempt 5) | 0.4 | — | Fallback: `gemini-1.5-flash` |
| **Anya wizard chat** (`/api/wizard-chat`) | **0.6** | **1024** | Conversational, friendly tone |
| **Anya post-gen chat** (`/api/chat-refine`) | **0.5** | **1024** | Semi-deterministic refinements |
| City recommendations | 0.4 | 1024 | Structured JSON output |
| Destination comparison | — | — | 10-param scoring |
| Trip extraction (Start Anywhere) | 0.1 | 512 | Near-deterministic extraction |

---

### RAG Architecture (Retrieval-Augmented Generation)

WanderPlan uses RAG to inject real traveller knowledge from Reddit and Wikivoyage into Gemini's itinerary generation prompt.

#### How It Works

```
1. INGESTION (startup + every 6h)
   ┌─────────────────────────────────────────────────┐
   │ scrapers/reddit.py                              │
   │   → Reddit JSON API (r/solotravel, r/travel...) │
   │   → chunk posts/comments by destination         │
   │   → embed via all-MiniLM-L6-v2 (384 dims)      │
   │   → upsert into Qdrant 'reddit' collection      │
   └─────────────────────────────────────────────────┘
   ┌─────────────────────────────────────────────────┐
   │ scrapers/wikivoyage.py                          │
   │   → scrape Wikivoyage sections (See, Eat, etc.) │
   │   → embed chunks                               │
   │   → upsert into Qdrant 'wiki' collection        │
   └─────────────────────────────────────────────────┘

2. RETRIEVAL (at itinerary generation time)
   services/search.py → retrieve_context(trip_config)
   │
   ├─ Build query: "{destination} {themes} travel tips"
   │    e.g. "Bali beach culture travel tips highlights activities food"
   │
   ├─ embed(query) → 384-dim vector
   │
   ├─ Qdrant cosine search (filtered by destination):
   │    reddit collection: top 10 hits
   │    wiki   collection: top 10 hits
   │
   └─ Return top-20 chunks sorted by score

3. AUGMENTATION (itinerary_chain.py)
   context_docs = await retrieve_context(trip_config)
   prompt = SYSTEM_PROMPT.format(
       context=format_docs(context_docs),
       trip_config=trip_config.model_dump_json()
   )
   → Gemini generates itinerary grounded in real traveller data
```

#### Example RAG Context Injection

**User trip:** Bali, 7 days, Beach + Culture themes

**Query sent to Qdrant:** `"Bali beach culture travel tips highlights activities food"`

**Retrieved chunks (sample):**

> *[reddit/solotravel]* "Ubud is the cultural heart — skip the rice terraces at 9am (tourist rush), go at 7am instead. Best warung meal I had was at Warung Babi Guling Ibu Oka near the palace." *(score: 0.91)*

> *[wikivoyage/Bali/See]* "Tanah Lot temple is best visited at sunset. Located on a rocky outcropping offshore, it is one of Bali's most photographed sites. The temple is accessible at low tide." *(score: 0.87)*

> *[reddit/travel]* "Hire a driver for the day (~$40 USD) rather than renting a scooter if you want to see Uluwatu + Kuta. Much safer and they know the timing for the Kecak fire dance." *(score: 0.84)*

**These chunks are injected into the Gemini prompt** under `DESTINATION RESEARCH:`, allowing the model to recommend Warung Babi Guling by name, suggest 7am rice terrace visits, and include Kecak fire dance as an evening activity.

If Qdrant is empty (cold start), the chain falls back to:
```
context = "No pre-fetched research available — use your own knowledge of the destination."
```

#### Embedding Model
- **Model:** `sentence-transformers/all-MiniLM-L6-v2`
- **Dimensions:** 384
- **Distance metric:** Cosine similarity
- **Runs locally** — no API key, no network call for embeddings

---

### System Prompt 1: Anya Wizard (`/api/wizard-chat`)

**File:** `apps/api/chains/wizard_chat_chain.py`  
**Temperature:** 0.6 · **Max tokens:** 1024  
**Version:** v3 (June 2026) — 9-section structured prompt

**Key sections:**
- **Persona & Tone** — warm Indian travel expert friend; 2-3 sentences max; TTS-optimised
- **Indian Cultural Context** — currency parsing (25k→25000, 1L→100000), travel seasons (Oct-Nov Diwali, Apr-May school holidays), joint family norms, veg/Jain food sensitivity
- **Audio/STT Handling** — Hinglish glossary (araam se→relaxed, family ke saath→family, bas karo→generate), filler word stripping (yaar, um, uh), incomplete sentence extraction, number speech (seven days→7)
- **6 Required Fields** — each with JSON key, valid values, and explicit phrase mappings
- **Optional Fields** — auto-inferred themes (honeymoon→wellness, adventure purpose→adventure)
- **Slot Filling** — never re-ask collected fields; defaults for "surprise me" (leisure, 6 days, 1L, moderate)
- **3-Stage Flow** — Stage 1: collect 6 fields → Stage 2: "anything else?" checkpoint → Stage 3: generate signal
- **config_patch Rules** — "include every extracted field even if you think it is already known"
- **Output Schema** — JSON only, includes `thought_process` for chain-of-thought reasoning

The backend `_has_all_required()` server-validates `ready_to_generate`. Stage 2 checkpoint is tracked via `_checkpoint_asked` flag in `partialConfig` and surfaced to the LLM via `CURRENT_STATE`.

---

### System Prompt 2: Anya Post-Gen Chat (`/api/chat-refine`)

**File:** `apps/api/chains/chat_refine_chain.py`  
**Temperature:** 0.5 · **Max tokens:** 1024  
**History:** Last 10 messages

```
You are Anya, WanderPlan's friendly AI travel assistant.

ROLE: Help refine the user's active trip plan. You can:
1. Answer travel questions factually.
2. Suggest changes to their trip configuration.
3. Detect when the user wants to change specific trip parameters.

CURRENT TRIP CONFIG:
{trip_config_json}

RESPONSE FORMAT — ONLY this JSON:
{
  "reply": "Your friendly reply (markdown ok)",
  "action_type": "none" | "patch_config" | "regenerate",
  "config_patch": null or { ...only changed fields... },
  "major_change": false
}

ACTION RULES:
- "none"         — general travel questions; no config change
- "patch_config" — small changes (pace, themes, accommodation); major_change: false
- "regenerate"   — destination/dates/group/budget >20% change; major_change: true
                   ask user to confirm before resetting itinerary

GUARDRAILS:
- Only answer travel-related questions
- Never make bookings or collect payment info
- Budget always in INR
- Keep replies concise and friendly

Non-travel response:
  "I'm Anya, WanderPlan's travel assistant — I can only help with travel questions! 🌍"
```

---

### System Prompt 3: Itinerary Generation (`/api/generate-itinerary`)

**File:** `apps/api/chains/itinerary_chain.py`  
**Temperature:** 0.4 · **Max tokens:** 16384

```
You are WanderPlan, an expert AI travel advisor.
Generate a detailed, realistic day-by-day travel itinerary based on the trip
configuration and destination research provided.

RULES:
- Output ONLY valid JSON matching the schema below. No prose, no markdown.
- Each day must have 3-6 activity items with realistic time allocations.
- Pace guide: relaxed=3-4 items/day, moderate=4-5, packed=5-6.
- Total activity costs must not exceed the stated budget.
- If kids are present: exclude bars, nightclubs, and extreme sports venues.
- If persona includes digital_nomad: add one 2-hour Work Block per day.
- If persona includes sports_fitness: add one Training Window per day.
- If persona includes pet_parent: only include dog_friendly venues.
- Tag photogenic/scenic spots with "instaworthy" in the tags array.
- Flag schedule conflicts (< 30 min transit gap) in transit_warnings.
- For local_name: provide place name in local script (e.g. 浅草寺).
- For youtube_search_query: generate a short, specific search phrase.
- For expense_breakdown: realistic INR estimates for all 8 cost categories.
- MULTI-HOP TRIPS: distribute days across all stops proportionally.

OUTPUT SCHEMA:
{ "days": [...], "expense_breakdown": {...} }

DESTINATION RESEARCH:
{context}   ← RAG-retrieved chunks from Qdrant (Reddit + Wikivoyage)

TRIP CONFIGURATION:
{trip_config}
```

---

## 9. Key Frontend Components

### `LandingHero.tsx`
Full landing page component with:
- Sticky nav with **Inspiration** and **FAQ** anchor links
- Hero H1 + primary CTA
- **Start Anywhere input** — URL/text box → `POST /api/extract-trip` → wizard preload
- Feature grid (4 cards)
- **Inspiration gallery** — 12 `InspirationCard` components (Wikipedia photos, click-to-preload)
- FAQ section (JSON-LD SEO)
- Footer CTA

**`InspirationCard`** (sub-component):
- Calls `useWikiImage(city)` for destination photo
- Shows gradient fallback while loading; replaces with real photo + hover zoom
- On click: calls `openWizardWithPreload({ city, country, days, label })` to pre-fill wizard

### `LLMWizard.tsx` ⭐ NEW (v5.0)
LLM-powered Anya wizard — replaces the scripted `ConversationalWizard`. Features:

- Chat bubbles (user + Anya) with typing indicator
- Dynamic chip suggestions returned by the LLM on each turn
- Field progress pills showing which of the 6 required fields are filled
- Voice input (Web Speech API) + TTS output (Speech Synthesis API)
- "Generate my itinerary" button appears once `ready_to_generate=true`
- Mobile-first: bottom-sheet on mobile, centered modal on desktop
- Calls `POST /api/wizard-chat` on each message; merges `config_patch` into local state
- On generate: merges partial config into `tripConfigStore` → calls `streamItinerary`

### `ConversationalWizard.tsx` (legacy, kept for reference)
~2400 lines. Original rule-based wizard (11 hardcoded field steps). No longer used by `page.tsx`.

### `ChatPanel.tsx`
Persistent post-generation Anya chat. Triggered by `FloatingAnyaButton` (floating orb).

Features:
- Design token styles (full dark mode support)
- Calls `POST /api/chat-refine` with current `tripConfig`
- `patch_config` action: silently applies changes
- `regenerate` action: shows confirmation dialog with "Yes, apply & reset" / "Just noting it"
- Typing indicator (3 bouncing dots)
- Persists message history in `chatStore` for the session

### `PolaroidCard.tsx`
Activity card with:
- Real `imageSrc` prop (Wikipedia photo or YouTube thumbnail)
- Gradient fallback via `pickGradient(title)` (deterministic hash)
- Hover zoom on real images
- `videoHref` → image area becomes a link with play badge
- Dark mode via CSS custom property tokens

### `BookingHub.tsx`
Collapsible section in Column 1. Features:
- Type selector chips (Flight / Hotel / Activity / Transport) with icon + color coding
- Confirmation number, date picker, amount fields
- Total tracked spend display
- Hover-to-reveal delete button per row
- `bookingStore` with `zustand/persist` → survives page refresh

### `ShareButton.tsx`
In ThreeColumnLayout center header. Click flow:
1. First click: calls `POST /api/share`, copies generated URL to clipboard
2. Subsequent clicks: copies cached URL (no re-request)
3. States: idle → loading → copied (green, 3s) / error (red, 2s)

### `ThreeColumnLayout.tsx`
Three-column dashboard + full-screen map mode. **Now mobile-responsive.**

Layout (desktop `lg+`):
- **Left (25%)**: `Column1Metrics` → metrics, expenses, currency, `BookingHub`
- **Center (flex-1)**: top-bar with destination + `ShareButton`, then `ItineraryTimeline` or `ComparisonPanel`
- **Right (25%)**: map + "⤢ Full screen" toggle, then `Column3Sidebar`

Layout (mobile `< lg`):
- **Bottom tab bar** with 3 tabs: Itinerary · Overview · Map & Tips
- Single scrollable panel showing the active tab's content
- "⤢ Full screen" map button still available in Map tab

Full-screen map (`step3View === 'map-full'`): renders `MapWrapper` full-height with day-tab toolbar (works on both mobile and desktop).

---

## 10. Hooks & Utilities

### `useWikiImage(city, country?)` — `hooks/useWikiImage.ts`
Shared hook for fetching Wikipedia destination photos.

```typescript
function useWikiImage(city: string, country?: string): string | null
```

- Calls Wikipedia `generator=search` API (free, no key, CORS-safe, `origin=*`)
- Endpoint: `https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch={city}+{country}+tourism+travel&gsrlimit=1&prop=pageimages&format=json&pithumbsize=600`
- Returns `null` while loading; caches in module-level `Map<string, string | null>`
- Used by: `InspirationCard` (LandingHero), `DestinationCard` (wizard), `PolaroidCard` (itinerary)

### `lib/api.ts`
All typed API calls. New functions in v3.0:

```typescript
extractTrip(input: string): Promise<ExtractedTrip>
shareTrip(payload): Promise<{ slug: string; url: string }>
getSharedTrip(slug: string): Promise<SharedTripData>
```

---

## 11. Voice Features

- **Input**: Web Speech API (`SpeechRecognition`) — Indian English, continuous mode
- **Output**: Speech Synthesis API — selects `en-IN` female voice, rate 1.05, pitch 1.15
- **ListeningOrb**: Animated gradient sphere indicating active voice mode
- **Auto-speak**: Latest bot message read aloud when voice mode is active
- Voice mode toggle in wizard header (LLMWizard); orb is `FloatingAnyaButton` on the itinerary screen

---

## 12. Data Flows

### Start Anywhere Flow (new)

```
User pastes URL/text → LandingHero input
  → handleStartAnywhere()
  → POST /api/extract-trip { input }
     ├─ Backend: if URL → httpx.get() → strip HTML → first 6000 chars
     └─ Gemini 2.5 Flash (temp 0.1) → ExtractedTrip JSON
  → if result.destination:
       openWizardWithPreload({ city, country, days, label })
       → wizard opens with pre-filled greeting
  → else: openWizard() (plain)
```

### Inspiration Card → Wizard Flow (new)

```
User clicks InspirationCard
  → InspirationCard.handleClick()
  → openWizardWithPreload({ city, country, days, label })
  → ConversationalWizard init effect detects wizardPreload
  → setDestination + updateDates + addLabel×2 + clearWizardPreload
  → Anya greets: "I see you're interested in [dest] for [N] days! ..."
  → wizard continues from 'purpose' step (destination already set)
```

### Post-Gen Chat Flow (new)

```
User clicks FloatingAnyaButton (after itinerary exists)
  → useChatStore.open()
  → ChatPanel renders (fixed bottom-right)
  → User types message
  → POST /api/chat-refine { messages, trip_config }
  → Gemini returns { reply, action_type, config_patch, major_change }
  ├─ action_type='none' → display reply only
  ├─ action_type='patch_config' → updateConfig(config_patch) silently
  └─ action_type='regenerate' → show confirmation dialog
       ├─ 'Yes, apply & reset' → updateConfig + resetItinerary
       └─ 'Just noting it' → dismiss
```

### Share Trip Flow (new)

```
User clicks ShareButton
  → reads itineraryStore.days + tripConfigStore.config + wizardChatStore.collectedLabels
  → POST /api/share { itinerary, trip_config, labels, destination_label }
     → backend: stores in _store dict, returns { slug: "a1b2c3d4", url: "/t/a1b2c3d4" }
  → navigator.clipboard.writeText(window.location.origin + url)
  → Button shows "Link copied!" (green) for 3s
  → Recipient visits /t/a1b2c3d4
     → SharedTripPage fetches GET /api/share/a1b2c3d4
     → Renders read-only day-by-day view
     → CTA: "Plan my own trip →" links to /
```

---

## 13. Environment Setup

### Backend (`apps/api/.env`)

```env
GEMINI_API_KEY=your_key_here
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-2.5-flash
QDRANT_URL=:memory:
ALLOWED_ORIGINS=http://localhost:3000
NOMINATIM_USER_AGENT=wanderplan/1.0
NOMINATIM_RATE_LIMIT=1
```

### Frontend (`apps/web/.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_MAPTILER_KEY=            # optional — default OSM tiles work without this
```

### Starting Servers

```bash
# Backend
cd apps/api && source .venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8000 --reload > /tmp/api.log 2>&1 &

# Frontend
cd apps/web && nohup npm run dev > /tmp/web.log 2>&1 &

# Health check
curl http://localhost:8000/health
```

---

## 14. Recent Changes (v5.0 & v6.0)

### v6.0 Changes (June 2026)

#### Anya Prompt v3 + Wizard Flow
| Change | Detail |
|---|---|
| **UPDATED** `chains/wizard_chat_chain.py` | System prompt fully rewritten into 9 structured sections covering persona, Indian context, Hinglish/STT handling, slot filling, 3-stage flow, and output schema |
| **NEW** `thought_process` field | `WizardChatResponse` now includes `thought_process: str | None`; logged at DEBUG level and returned in the API response |
| **UPDATED** 3-stage flow | Stage 1 collects 6 required fields, Stage 2 triggers a one-time "anything else?" checkpoint, Stage 3 enables generation only after confirmation |
| **UPDATED** frontend/backend state | `_checkpoint_asked` is stored in `partialConfig`, surfaced to the LLM via `CURRENT_STATE`, and used to gate `ready_to_generate` |
| **FIXED** wizard resilience | Empty-message bootstrap seeding, regex-based JSON fence parsing, stale closure via `partialConfigRef`, generate-loop chip filtering, Gemini error fallback to mock, and better frontend 429/retry UX |

### v5.0 Changes (June 2026)

#### LLM-Powered Anya Wizard
| Change | Detail |
|---|---|
| **NEW** `LLMWizard.tsx` | Replaces scripted state machine. Anya now uses Gemini 2.5 Flash to collect trip fields conversationally. One message can fill multiple fields. |
| **NEW** `chains/wizard_chat_chain.py` | Full system prompt + field extraction logic + `_has_all_required()` server-side validation |
| **NEW** `routers/wizard_chat.py` | `POST /api/wizard-chat` endpoint |
| **UPDATED** `lib/api.ts` | Added `wizardChat()` function + `WizardChatResponse` type |
| **UPDATED** `app/page.tsx` | Swapped `<ConversationalWizard>` → `<LLMWizard>` |

#### Mobile-Responsive Redesign
| Change | Detail |
|---|---|
| **UPDATED** `ThreeColumnLayout.tsx` | Bottom tab nav on mobile (`< lg`); 3-column on desktop (`lg+`) |
| **UPDATED** `ConversationalWizard.tsx` | Full-screen on mobile, reduced padding |
| **REMOVED** `MobileWarningBanner` | Removed from `layout.tsx` — no longer needed |

### v4.0 Changes (June 2026)

#### New API Endpoints
| Endpoint | Purpose |
|---|---|
| `POST /api/extract-trip` | URL/text → structured trip fields via Gemini |
| `POST /api/share` | Serialize trip → 8-char slug |
| `GET /api/share/{slug}` | Read-only trip data for `/t/[slug]` page |

#### New Backend Files
| File | Purpose |
|---|---|
| `chains/extract_trip_chain.py` | URL fetch + Gemini extraction logic |
| `routers/extract_trip.py` | FastAPI router for `/api/extract-trip` |
| `routers/share.py` | FastAPI router for `/api/share` (in-memory store) |
| `services/geocode.py` | Added `is_country` detection from Nominatim address |
| `models/common.py` | `GeocodeResponse.is_country: bool` |

#### New Frontend Files
| File | Purpose |
|---|---|
| `hooks/useWikiImage.ts` | Shared Wikipedia photo hook (extracted from wizard) |
| `components/common/ShareButton.tsx` | One-click trip link generator |
| `components/dashboard/BookingHub.tsx` | Booking tracker component |
| `store/bookingStore.ts` | Zustand + localStorage booking store |
| `app/t/[slug]/page.tsx` | Read-only shared trip view |

#### Modified Frontend Files
| File | Change |
|---|---|
| `store/appStore.ts` | Added `wizardPreload`, `openWizardWithPreload`, `clearWizardPreload` |
| `components/common/LandingHero.tsx` | Start Anywhere input, nav anchors, inspiration preload |
| `components/common/FloatingAnyaButton.tsx` | Opens `chatStore` (not wizard) when itinerary exists |
| `components/chat/ChatPanel.tsx` | Rebuilt with design tokens, renamed to Anya |
| `components/layout/ThreeColumnLayout.tsx` | Added ShareButton header bar in center column |
| `components/dashboard/Column1Metrics.tsx` | Added `<BookingHub />` at bottom |
| `lib/api.ts` | Added `extractTrip()`, `shareTrip()`, `getSharedTrip()`, `is_country` type |
| `app/page.tsx` | Added `<ChatPanel />` alongside `FloatingAnyaButton` |
