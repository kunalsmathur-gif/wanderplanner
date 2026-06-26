# WanderPlan — Technical Documentation

**Version:** 4.0 (Competitor Parity: Persistent Chat · Share · Start Anywhere · Booking Hub)  
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
8. [AI Models & Prompt Design](#8-ai-models--prompt-design)
9. [Key Frontend Components](#9-key-frontend-components)
10. [Hooks & Utilities](#10-hooks--utilities)
11. [Voice Features](#11-voice-features)
12. [Data Flows](#12-data-flows)
13. [Environment Setup](#13-environment-setup)
14. [Recent Changes (v3.0)](#14-recent-changes-v30)

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
│   │   └── ThreeColumnLayout.tsx — 3-col layout + full-screen map mode + share button
│   └── wizard/
│       └── ConversationalWizard.tsx — Full chat wizard (2400+ lines)
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
  └── <ConversationalWizard />      when wizardOpen (fixed inset overlay)
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
│   └── config.py             — Settings (env vars)
├── chains/
│   ├── itinerary_chain.py    — Gemini 2.5 Flash itinerary gen (5× retry + fallback)
│   ├── chat_refine_chain.py  — Anya post-gen chat (patch_config / regenerate actions)
│   ├── extract_trip_chain.py — URL/text → structured trip fields (Start Anywhere)
│   └── ...
├── routers/
│   ├── itinerary.py          — POST /api/generate-itinerary (SSE streaming)
│   ├── chat_refine.py        — POST /api/chat-refine
│   ├── extract_trip.py       — POST /api/extract-trip
│   ├── share.py              — POST /api/share + GET /api/share/{slug}
│   ├── geocode.py            — GET /api/geocode (Nominatim proxy)
│   ├── recommend_cities.py   — POST /api/recommend-cities
│   ├── comparison.py         — POST /api/compare-destinations
│   ├── travel_tips.py        — GET /api/travel-tips
│   ├── best_time.py          — GET /api/best-time/{city}
│   └── ...
├── services/
│   └── geocode.py            — Nominatim proxy (1 req/s rate limit, LRU cache, is_country detection)
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

## 8. AI Models & Prompt Design

### Primary: Gemini 2.5 Flash

Used for all LLM tasks:
- Itinerary generation (structured JSON output, 5-attempt retry)
- Chat refinement (Anya post-gen chat)
- City recommendations
- Destination comparison
- Travel tips generation
- **NEW**: Trip extraction from URLs/text

### Retry & Fallback Chain (Itinerary)

```
Attempt 1-3: gemini-2.5-flash (temperature 0.7)
Attempt 4:   gemini-2.5-flash-lite (simpler schema)
Attempt 5:   gemini-1.5-flash (fallback)
```

### Extract Trip Prompt (Start Anywhere)

System prompt instructs Gemini to parse free-form travel content and return:
`destination`, `destination_country`, `duration_days`, `themes[]`, `budget_inr`, `summary`

Temperature: 0.1 (low — deterministic extraction). Max tokens: 512.

### Chat Refine Response Format

```json
{
  "reply": "Friendly markdown response",
  "action_type": "none | patch_config | regenerate",
  "config_patch": { "budget": { "amount": 100000 } },
  "major_change": false
}
```

`action_type`:
- `none` — informational reply only
- `patch_config` — silently applies `config_patch` to `tripConfigStore`
- `regenerate` — prompts user confirmation dialog before resetting itinerary

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

### `ConversationalWizard.tsx`
~2400 lines. Full chat wizard handling 11 input fields, voice mode, edit-entry flow.

**Wizard Preload** (new):
On `wizardOpen` with `wizardPreload !== null`:
1. Pre-sets `tripConfigStore` destination + duration
2. Adds `collectedLabels` for those fields
3. Shows personalized greeting: *"I see you're interested in [dest] for [N] days!"*
4. Clears preload via `clearWizardPreload()`

**Country Auto-Detection** (new):
When user types a destination in `fixed` mode, `resolvePlace()` now returns `isCountry`. If true:
1. Switches `destination_mode` to `'country'`
2. Calls `recommendCities()` for that country
3. Shows multi-city chip selection

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
Three-column dashboard + full-screen map mode.

Layout:
- **Left (20%)**: `Column1Metrics` → metrics, expenses, currency, `BookingHub`
- **Center (55%)**: top-bar with destination + `ShareButton`, then `ItineraryTimeline` or `ComparisonPanel`
- **Right (25%)**: map + "⤢ Full screen" toggle, then `Column3Sidebar`

Full-screen map (`step3View === 'map-full'`): renders `MapWrapper` full-height with day-tab toolbar.

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
- **Output**: Speech Synthesis API — selects `en-IN` female voice, rate 0.9, pitch 1.1
- **ListeningOrb**: Animated gradient sphere indicating active voice mode
- **Auto-speak**: Latest bot message read aloud when voice mode is active
- Voice mode toggle in wizard header; orb is `FloatingAnyaButton` on the itinerary screen

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

## 14. Recent Changes (v3.0)

### New API Endpoints
| Endpoint | Purpose |
|---|---|
| `POST /api/extract-trip` | URL/text → structured trip fields via Gemini |
| `POST /api/share` | Serialize trip → 8-char slug |
| `GET /api/share/{slug}` | Read-only trip data for `/t/[slug]` page |

### New Backend Files
| File | Purpose |
|---|---|
| `chains/extract_trip_chain.py` | URL fetch + Gemini extraction logic |
| `routers/extract_trip.py` | FastAPI router for `/api/extract-trip` |
| `routers/share.py` | FastAPI router for `/api/share` (in-memory store) |
| `services/geocode.py` | Added `is_country` detection from Nominatim address |
| `models/common.py` | `GeocodeResponse.is_country: bool` |

### New Frontend Files
| File | Purpose |
|---|---|
| `hooks/useWikiImage.ts` | Shared Wikipedia photo hook (extracted from wizard) |
| `components/common/ShareButton.tsx` | One-click trip link generator |
| `components/dashboard/BookingHub.tsx` | Booking tracker component |
| `store/bookingStore.ts` | Zustand + localStorage booking store |
| `app/t/[slug]/page.tsx` | Read-only shared trip view |

### Modified Frontend Files
| File | Change |
|---|---|
| `store/appStore.ts` | Added `wizardPreload`, `openWizardWithPreload`, `clearWizardPreload` |
| `components/common/LandingHero.tsx` | Start Anywhere input, nav anchors, inspiration preload |
| `components/common/FloatingAnyaButton.tsx` | Opens `chatStore` (not wizard) when itinerary exists |
| `components/chat/ChatPanel.tsx` | Rebuilt with design tokens, renamed to Anya |
| `components/layout/ThreeColumnLayout.tsx` | Added ShareButton header bar in center column |
| `components/dashboard/Column1Metrics.tsx` | Added `<BookingHub />` at bottom |
| `components/wizard/ConversationalWizard.tsx` | Preload handling, country auto-detect, shared hook |
| `lib/api.ts` | Added `extractTrip()`, `shareTrip()`, `getSharedTrip()`, `is_country` type |
| `app/page.tsx` | Added `<ChatPanel />` alongside `FloatingAnyaButton` |
