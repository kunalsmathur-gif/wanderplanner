# WanderPlan — Technical Documentation

**Version:** 3.0 (Logo · SEO · Gemini 2.5 · Dark Mode Fixes)  
**Last Updated:** June 24, 2026  
**Status:** Production-ready with AI voice assistant

---

## Table of Contents

1. [Overview](#overview)
2. [Tech Stack](#tech-stack)
3. [Design System](#design-system)
4. [Architecture](#architecture)
5. [APIs & External Services](#apis--external-services)
6. [AI Models & LLMs](#ai-models--llms)
7. [Frontend Components](#frontend-components)
8. [Backend Services](#backend-services)
9. [Voice Features](#voice-features)
10. [Data Flow](#data-flow)
11. [Environment Setup](#environment-setup)
12. [Recent Updates](#recent-updates)

---

## Overview

WanderPlan is an AI-powered travel planning platform that uses conversational AI (Anya) to help users plan personalized trips. The platform features:

- **Conversational wizard** with voice interaction (Anya - AI Travel Assistant)
- **AI-generated itineraries** with day-by-day schedules
- **Destination comparison** tools
- **Real-time travel tips** from community sources
- **Interactive maps** with itinerary visualization
- **One-screen interface** with chat overlay

---

## Tech Stack

### Frontend Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| **Next.js** | 16.2.9 | React framework with App Router, Turbopack |
| **TypeScript** | 5.x | Type-safe development |
| **Tailwind CSS** | 4.x | Utility-first styling |
| **Zustand** | 5.x | Lightweight state management |
| **React Leaflet** | 4.x | Interactive maps (OpenStreetMap) |
| **Axios** | 1.x | HTTP client with interceptors |
| **Web Speech API** | Native | Speech recognition (voice input) |
| **Speech Synthesis API** | Native | Text-to-speech (voice output) |

**Frontend Build Tools:**
- Turbopack (Next.js 16 bundler)
- PostCSS with Tailwind
- TypeScript compiler

### Backend Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.9+ | Core language |
| **FastAPI** | 0.111+ | Async REST API framework |
| **Uvicorn** | - | ASGI server |
| **Pydantic** | 2.x | Data validation and serialization |
| **Google Generative AI** | Latest | Gemini API client |
| **Qdrant** | 1.x | Vector database (in-memory mode) |
| **sentence-transformers** | - | Text embeddings (all-MiniLM-L6-v2) |
| **httpx** | - | Async HTTP client for scraping |
| **BeautifulSoup4** | - | HTML parsing |
| **APScheduler** | - | Background job scheduling |

---

## Design System

### Visual Identity (v3.0 Brand & SEO Refresh)

WanderPlan now uses a cleaner luxury-travel visual system centered on a geometric gold W brand mark, high-contrast typography, and fully synchronized light/dark mode behavior.

#### Brand Mark

Brand mark: Geometric gold W with cross-diagonal diamond intersection nodes and compass arrow. Dual-tone gold (warm muted in light mode, bright metallic in dark mode). Wordmark in dark navy (light) / gold (dark). Tagline "Curated AI Travel Planning" at md/lg sizes.

- **SVG viewBox**: `0 0 72 58`
- **Key nodes**: diamond intersections at `(27,27)` and `(41,27)`, inner peak at `(34,8)`, compass arrow at top-right `(62,6)`
- **Sizes**: `sm {h:28, w:35}`, `md {h:36, w:45}`, `lg {h:48, w:60}`

#### Color Palette

**Core Colors:**
- **Sky Blue** `#0EA5E9` — primary CTA, links, progress fills
- **Adventure Orange** `#EA580C` — accent highlights
- **Ocean Navy** `#0C4A6E` — headings, wordmark on light mode
- **Soft Gold** `#A8820A → #C9A227 → #DFB84A` — brand gradient in light mode
- **Metallic Gold** `#F5D060 → #D4AF37 → #B89020` — brand gradient in dark mode

#### Typography

**Three-font System:**

1. **Space Grotesk** (Display / wordmark)
   - Used for headers, logo wordmark, strong CTAs
   - Crisp geometric feel aligned with the new brand mark

2. **DM Sans** (Body)
   - Used for interface copy, labels, helper text, FAQs
   - Balanced for dense trip-planning UI

3. **JetBrains Mono** (Data)
   - Used for technical or structured values where alignment matters

#### Theme System

- `ThemeToggle.tsx` uses a `MutationObserver` on `document.documentElement` to track `class` changes
- Toggle reads live DOM state on click, avoiding stale React closure bugs
- Theme persistence key: `wp-theme` (`dark` / `light`)
- Blocking head script applies theme before first paint to prevent flash

---

## Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (Desktop)                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           Next.js 16 (Turbopack)                       │ │
│  │                                                         │ │
│  │  ┌────────────────────────────────────────────────┐   │ │
│  │  │  ConversationalWizard (Anya) - Overlay         │   │ │
│  │  │  • Chat interface with voice I/O              │   │ │
│  │  │  • Speech Recognition API                      │   │ │
│  │  │  • Speech Synthesis API (Indian female voice) │   │ │
│  │  │  • Wizard flow: purpose → dates → destination │   │ │
│  │  └────────────────────────────────────────────────┘   │ │
│  │                                                         │ │
│  │  ┌──────────┐  ┌──────────────────┐  ┌────────────┐  │ │
│  │  │ Column 1 │  │    Column 2       │  │  Column 3  │  │ │
│  │  │ (20%)    │  │    (55%)          │  │  (25%)     │  │ │
│  │  │          │  │                   │  │            │  │ │
│  │  │ Metrics  │  │ Itinerary         │  │ Map        │  │ │
│  │  │ Booking  │  │ Timeline          │  │ Best Time  │  │ │
│  │  │ Expenses │  │ Comparison        │  │ Tips       │  │ │
│  │  └──────────┘  └──────────────────┘  └────────────┘  │ │
│  │                                                         │ │
│  │  Zustand: tripConfigStore, wizardChatStore,           │ │
│  │           itineraryStore, appStore                     │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTPS / JSON
┌─────────────────────▼───────────────────────────────────────┐
│              FastAPI Backend (Port 8000)                     │
│                                                              │
│  Routers:                                                    │
│  • /api/generate-itinerary   → Gemini 2.5 Flash (5x retry) │
│  • /api/chat-refine          → Anya conversational AI       │
│  • /api/recommend-cities     → City suggestions              │
│  • /api/travel-tips          → Gemini-generated tips        │
│  • /api/best-time/{city}     → Historical weather data      │
│  • /api/geocode              → Nominatim wrapper (en names) │
│  • /api/youtube-thumbnail    → YouTube search scraper       │
│                                                              │
│  Background Jobs:                                            │
│  • Reddit content refresh (every 6 hours)                   │
│  • Qdrant vector ingestion                                   │
└──────┬──────────────┬─────────────────┬────────────────────┘
       │              │                 │
┌──────▼──────┐ ┌─────▼──────┐ ┌───────▼──────┐
│   Qdrant    │ │   Gemini   │ │  External    │
│ (in-memory) │ │  2.5 Flash │ │  APIs        │
│             │ │  (primary) │ │              │
│ Collections:│ │  lite/1.5  │ │ • Nominatim  │
│ • reddit    │ │  fallback  │ │ • Open-Meteo │
│ • wiki      │ │            │ │ • YouTube    │
│             │ │            │ │ • Reddit JSON│
└─────────────┘ └────────────┘ └──────────────┘
```

### Three-Column Layout

**Left Column (20%)**: Trip Metrics, Expense Breakdown, Currency  
**Center Column (55%)**: Itinerary Timeline, Comparison Panel  
**Right Column (25%)**: Map, Best Time Widget, Booking Links, Travel Tips

---

## APIs & External Services

### External APIs Used

| API | Purpose | Authentication | Rate Limits | Cost |
|-----|---------|----------------|-------------|------|
| **Google Gemini API** | LLM for itinerary generation, chat refinement, travel tips | API Key (`GEMINI_API_KEY`) | Generous free tier | ~₹0.01/request |
| **Nominatim (OSM)** | Geocoding (city → lat/lon) | None | 1 req/sec | Free |
| **Open-Meteo** | Historical weather data | None | Unlimited | Free |
| **Reddit JSON API** | Community travel tips fallback | None | 60 req/min | Free |
| **YouTube** | Video search/thumbnails | None (web scraping) | N/A | Free |
| **OpenStreetMap Tiles** | Map rendering | None | Fair use | Free |

### Backend API Endpoints

#### Itinerary Generation
- `POST /api/generate-itinerary`
  - **Input**: `TripConfig` (purpose, dates, destination, budget, group, etc.)
  - **Output**: Streaming JSON with day-by-day itinerary
  - **Model**: Gemini 2.5 Flash
  - **Processing**: ~30-60 seconds for 5-7 day trip

#### Conversational Chat
- `POST /api/chat-refine`
  - **Input**: Chat messages + current `TripConfig`
  - **Output**: `{reply, action_type, config_patch, major_change}`
  - **Model**: Gemini 2.5 Flash
  - **Purpose**: Anya's conversational responses and config updates

#### City Recommendations
- `POST /api/recommend-cities`
  - **Input**: Country name or travel preferences
  - **Output**: List of recommended cities with descriptions
  - **Model**: Gemini 2.5 Flash

#### Travel Tips
- `GET /api/travel-tips?destination=X&limit=N`
  - **Primary**: Gemini-generated community-style tips (cached)
  - **Secondary**: Reddit JSON API 
  - **Fallback**: Curated generic travel tips (6 templates)
  - **Cache**: In-memory per destination
  - **Cost**: ~₹0.01/destination (cached indefinitely)
  - **Output**: `{tips: [TravelTip], destination: string}`
  - **TravelTip**: `{title, text_preview, post_url, source, score, thumbnailUrl?}`
  - **YouTube Integration**: Frontend fetches `/api/youtube-thumbnail` for each tip

#### Geocoding
- `GET /api/geocode?q=city_name`
  - **Proxy**: Nominatim (OpenStreetMap)
  - **Headers**: `Accept-Language: en`
  - **Params**: `namedetails=1`
  - **Name priority**: `name:en` → address city/town/village → `display_name`
  - **Returns**: `{city, country, lat, lon}`

#### Weather Data
- `GET /api/best-time/{city}`
  - **Source**: Open-Meteo Historical Weather API
  - **Returns**: Monthly temperature/rainfall averages

#### YouTube Thumbnails
- `GET /api/youtube-thumbnail?q=search_query`
  - **Method**: Web scraping YouTube search results
  - **Returns**: `{videoId, thumbnailUrl}`

---

## AI Models & LLMs

### Primary Model: Google Gemini 2.5 Flash

**Model ID**: `gemini-2.5-flash`

**Fallback chain:**
1. `gemini-2.5-flash`
2. `gemini-2.5-flash-lite-preview-06-17`
3. `gemini-1.5-flash`

**Retry strategy:**
- Up to **5 attempts** per model
- Exponential backoff: **5 / 10 / 20 / 40 / 60 seconds**
- Broader exception matching for transient quota / availability failures: `503`, `UNAVAILABLE`, `429`, `RESOURCE_EXHAUSTED`
- Same retry/fallback pattern used in both `chains/itinerary_chain.py` and `services/comparison.py`

**Use Cases:**
1. **Itinerary Generation** (`generate_itinerary.py`)
   - Prompt: Structured JSON output with day-by-day schedule
   - Temperature: 0.7
   - Max tokens: 4096
   - Includes: Activities, timings, transit, YouTube search queries

2. **Chat Refinement** (`chat_refine_chain.py`)
   - Prompt: Anya's persona, trip context, action detection
   - Temperature: 0.5
   - Max tokens: 1024
   - Returns: Reply + config patch + regeneration flag

3. **City Recommendations** (`recommend_cities.py`)
   - Prompt: Country/preferences → 3-5 city suggestions
   - Temperature: 0.7
   - Format: JSON with city names + descriptions

4. **Travel Tips** (`travel_tips.py`)
   - Prompt: Generate 6 authentic community-style tips
   - Temperature: 0.8
   - Caching: In-memory per destination
   - Fallback: Reddit JSON if Gemini fails

### Embeddings Model

**Model**: `sentence-transformers/all-MiniLM-L6-v2`  
**Purpose**: Text embeddings for semantic search in Qdrant  
**Dimensions**: 384  
**Runtime**: Local (no API calls)

---

## Frontend Components

### Core Components

#### 1. ConversationalWizard (`apps/web/components/wizard/ConversationalWizard.tsx`)
**Purpose**: Main chat interface with Anya (AI assistant)

**Features:**
- Full conversational wizard flow
- Voice input (Web Speech API)
- Voice output (Speech Synthesis API)
- Quick-reply chips for common inputs
- City suggestions via Gemini
- Multi-select themes
- Trip summary card with generate button
- Stays open after itinerary generation
- Sky-blue progress bar track (`bg-[var(--color-primary)]/20`)
- Gradient fill from `var(--color-primary)` to `#38bdf8` with glow shadow
- CounterCard contrast fix with explicit Tailwind light/dark classes
- Comparison view expanded from 3 to 10 qualitative parameters

**Wizard Fields:**
1. `purpose` → Purpose of trip (chips: Leisure, Adventure, Honeymoon, etc.)
2. `origin` → Departure city (geocoding)
3. `destination_mode` → Fixed city / Country / Exploring
4. `destination` → Final destination
5. `city_selection` → (if country mode) City picker
6. `dates` → Travel dates (preset or custom)
7. `group` → Group composition (adults, kids, seniors, pets)
8. `budget` → Budget amount (INR)
9. `accommodation` → Hotel, Airbnb, Hostel, Resort, etc.
10. `pace` → Relaxed, Moderate, Packed
11. `themes` → Multi-select (Culture, Food, Adventure, etc.)
12. `refinement` → Final refinements before generation
13. `summary` → Review all inputs + Generate/View buttons

**Voice Mode:**
- Single animated button (🎙️ pulsating)
- Activates both listening and speaking
- Auto-restarts listening after each response
- Female Indian voice (age 20-25), pitch 1.15, rate 1.05

#### 2. WanderplanLogo (`apps/web/components/common/WanderplanLogo.tsx`)
**Purpose**: Shared brand mark across landing page and app chrome

**Features:**
- Geometric gold W mark with 5-point spine path, two cross-diagonals, diamond nodes, and compass arrow
- SVG viewBox `0 0 72 58`
- Dual-mode gold gradients optimized separately for light and dark surfaces
- Optional uppercase wordmark and tagline

#### 3. ThemeToggle (`apps/web/components/common/ThemeToggle.tsx`)
**Purpose**: Global theme switch for landing and itinerary views

**Architecture:**
- `MutationObserver` watches `document.documentElement.className`
- Toggle reads live DOM state with `!html.classList.contains('dark')`
- React state updates only from observer callback to prevent double-writes
- Adaptive border/text colors work on mixed backgrounds

#### 4. LandingHero (`apps/web/components/common/LandingHero.tsx`)
**Purpose**: Landing page hero, SEO surface, and entry point to the wizard

**Features:**
- Sticky top nav with `WanderplanLogo size="md"`, `ThemeToggle`, and primary CTA
- Card-style example trip chips with emoji, two-line labels, hover lift, and “Plan this →” reveal
- Crawlable eyebrow text: `Wanderplan · Free AI Travel Planner`
- Full FAQ section aligned with JSON-LD schema for rich results

#### 5. ThreeColumnLayout (`apps/web/components/layout/ThreeColumnLayout.tsx`)
**Purpose**: Main itinerary view layout

**Columns:**
- **Left (20%)**: `Column1Metrics` - Metrics, Expenses, Currency (Visa / eSIM / Activities removed)
- **Center (55%)**: `ItineraryTimeline` or `ComparisonPanel`
- **Right (25%)**: `Column3Sidebar` - Map, Best Time, Booking Links, Travel Tips

#### 6. ItineraryTimeline (`apps/web/components/itinerary/ItineraryTimeline.tsx`)
**Purpose**: Day-by-day itinerary display

**Features:**
- Day tabs with activity counts
- Activity cards with timings
- Transit warnings
- YouTube video embeds (when available)
- Location pins synced with map

#### 7. MapWrapper (`apps/web/components/map/MapWrapper.tsx`)
**Purpose**: Interactive Leaflet map

**Features:**
- OpenStreetMap tiles
- Activity markers
- Click to select day
- Zoom to bounds on load

#### 8. BookingLinksSection (`apps/web/components/itinerary/BookingLinksSection.tsx`)
**Purpose**: Flight, hotel, activity booking links

**Providers:**
- Skyscanner (flights)
- Booking.com (hotels)
- Viator (activities)

### State Management (Zustand)


#### 1. `tripConfigStore.ts`
```typescript
interface TripConfig {
  purpose: string
  dates: { start: string | null, end: string | null, flexible: boolean }
  origin: { city, lat, lon }
  destination: { city, country, lat, lon } | null
  destination_mode: 'fixed' | 'exploring' | 'country'
  group: { infants, kids, adults, seniors, pets }
  accommodation: { style[], min_bedrooms, ... }
  pace: 'relaxed' | 'moderate' | 'packed'
  budget: { amount, currency }
  themes: string[]
  personas: string[]
}
```

#### 2. `wizardChatStore.ts`
```typescript
interface WizardChatStore {
  messages: WizardMessage[]  // {role: 'user'|'bot', content, chips?, inputType?}
  currentField: WizardField | null
  phase: 'chatting' | 'summary' | 'generating' | 'done'
  collectedLabels: Record<string, string>  // User-friendly labels
}
```

#### 3. `itineraryStore.ts`
```typescript
interface ItineraryStore {
  days: ItineraryDay[]  // {date, items[]}
  activeDay: number
  isLoading: boolean
  error: string | null
}
```

#### 4. `appStore.ts`
```typescript
interface AppStore {
  wizardOpen: boolean
  step3View: 'itinerary' | 'comparison'
  openWizard() / closeWizard()
}
```

---

## Backend Services

### Core Services

#### 1. Itinerary Generation (`chains/generate_itinerary.py`)
**Model**: Gemini 2.5 Flash  
**Input**: `TripConfig` (validated Pydantic model)  
**Output**: Streaming JSON chunks  
**Process**:
1. Context retrieval from Qdrant (Reddit/Wikivoyage)
2. Persona-aware prompt construction
3. Day-by-day activity generation with timings
4. Transit feasibility checks
5. YouTube search query generation
6. Budget allocation per activity

**Prompt Template**:
```python
f"""You are an expert travel planner. Generate a {duration}-day itinerary for {destination}.

User Profile:
- Purpose: {purpose}
- Group: {group_composition}
- Pace: {pace}
- Budget: {currency} {amount}
- Themes: {themes}

Context from travelers:
{qdrant_results}

Output JSON format:
{{
  "days": [
    {{
      "date": "YYYY-MM-DD",
      "items": [
        {{
          "time": "HH:MM",
          "title": "Activity name",
          "description": "Details",
          "cost_estimate": number,
          "duration_minutes": number,
          "location": {{"lat": X, "lon": Y, "address": "..."}},
          "youtube_search_query": "...",
          "tags": ["..."]
        }}
      ]
    }}
  ]
}}
"""
```

#### 2. Chat Refinement (`chains/chat_refine_chain.py`)
**Model**: Gemini 2.5 Flash  
**Persona**: Anya - friendly AI travel assistant  
**Temperature**: 0.5  

**Action Types**:
- `none`: General travel questions (no config change)
- `patch_config`: Minor changes (pace, themes, accommodation)
- `regenerate`: Major changes (destination, dates, group, budget >20%)

**Response Format**:
```json
{
  "reply": "Conversational response from Anya",
  "action_type": "patch_config",
  "config_patch": {"pace": "relaxed"},
  "major_change": false
}
```

#### 3. Qdrant Vector Store (`services/qdrant_service.py`)
**Mode**: In-memory (`:memory:`)  
**Collections**:
- `reddit_highlights` (1000+ posts)
- `wikivoyage_content` (500+ destination pages)

**Embedding Model**: `all-MiniLM-L6-v2` (384 dimensions)  
**Search**: Semantic similarity with score threshold 0.1

#### 4. Reddit Scraper (`routers/reddit_highlights.py`)
**Source**: Reddit JSON API (`/r/travel/search.json`)  
**Refresh**: Every 6 hours (APScheduler)  
**Filtering**: 
- Minimum score: 50
- Content profanity filter
- Relevance threshold: 0.1

**Fallback**: When Reddit is down/blocked, returns cached results

#### 5. Travel Tips (`routers/travel_tips.py`)
**Primary**: Gemini-generated community-style tips  
**Cache**: In-memory dictionary `{destination: tips[]}`  
**Fallback**: Reddit JSON API  
**Cost**: ~₹0.01 per destination (one-time, cached indefinitely)

**Gemini Prompt**:
```python
f"""Generate 6 authentic travel tips for {destination} as if from Reddit/travel forums.
Include:
- Hidden gems locals recommend
- Money-saving hacks
- Must-try foods
- Transportation tips
- Safety advice
- Best areas to stay

Format as community posts with upvotes (20-500 range).
"""
```

---

## Voice Features

### Anya - AI Voice Assistant

**Introduction**:
When wizard opens: "Hi! I'm Anya from WanderPlan 👋\n\nI'm here to help you plan your perfect trip. Let's get started!"

### Speech Recognition (Voice Input)

**API**: Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`)  
**Language**: `en-IN` (Indian English)  
**Mode**: Continuous listening when voice mode active  
**Trigger**: Single animated button (🎙️)

**Auto-Loop**: After each response, automatically restarts listening if voice mode is still active

### Speech Synthesis (Voice Output)

**API**: Browser Speech Synthesis API (`SpeechSynthesisUtterance`)  
**Voice Selection Priority**:
1. Indian English female voices (`en-IN` + `female` in name)
2. Any English female voice
3. Google/Microsoft Indian voices

**Voice Characteristics**:
- **Language**: `en-IN`
- **Pitch**: 1.15 (higher for young female)
- **Rate**: 1.05 (slightly faster - energetic)
- **Volume**: 1.0
- **Target Age**: 20-25 years old
- **Gender**: Female
- **Accent**: Indian

**Text Cleanup**:
- Strips markdown formatting (`*`, `_`, `~`, `` ` ``, `#`)
- Removes link syntax `[text](url)` → text
- Removes emojis and special characters for cleaner speech

**Visual Feedback**:
- Animated pulsating button when active
- Purple/blue gradient background
- Ping animation rings
- Button changes from 🔈 to 🔊 when speaking

---

## Data Flow

### 1. Itinerary Generation Flow

```
User completes wizard → Anya asks refinement → Generate clicked
         │
         ▼
TripConfig assembled in Zustand
         │
         ▼
POST /api/generate-itinerary
         │
         ├→ Qdrant semantic search (Reddit + Wikivoyage)
         ├→ Gemini 2.5 Flash prompt construction
         ├→ Streaming JSON generation (30-60s)
         └→ YouTube search query generation
         │
         ▼
Frontend receives SSE stream
         │
         ├→ Parses JSON chunks
         ├→ Updates itineraryStore
         ├→ Geocodes activity locations
         └→ Renders timeline + map pins
```

### 2. Voice Interaction Flow

```
User clicks voice button
         │
         ▼
Voice mode activated
         │
         ├→ Speech Synthesis speaks last bot message
         └→ Speech Recognition starts listening
         │
         ▼
User speaks response
         │
         ▼
Transcript captured → Input field populated → Send
         │
         ▼
POST /api/chat-refine (if in summary phase)
  OR
Direct wizard field handler
         │
         ▼
Anya responds (text + TTS)
         │
         ├→ Apply config_patch if any
         ├→ Move to next wizard field
         └→ Auto-restart listening (voice mode loop)
```

### 3. Travel Tips Flow

```
Destination entered
         │
         ▼
GET /api/travel-tips?destination=X
         │
         ├→ Check in-memory cache
         │   └→ If found: return cached tips
         │
         ├→ If not cached:
         │   ├→ Call Gemini 2.5 Flash (~₹0.01)
         │   ├→ Generate 6 community-style tips
         │   ├→ Cache result in memory
         │   └→ Return tips
         │
         └→ Fallback: Reddit JSON API (if Gemini fails)
```

---

## Environment Setup

### Frontend Environment Variables (`apps/web/.env.local`)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Backend Environment Variables (`apps/api/.env`)

```bash
# LLM Provider
LLM_PROVIDER=gemini  # or 'mock' for testing
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Qdrant
QDRANT_URL=:memory:  # or http://localhost:6333 for persistent

# CORS
ALLOWED_ORIGINS=http://localhost:3000,https://wanderplan.vercel.app

# Optional
INGESTION_REFRESH_HOURS=6
CONTENT_FILTER_LEVEL=strict
```

### Running Locally

**Backend:**
```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:**
```bash
cd apps/web
npm install
npm run dev  # Port 3000
```

**Access:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## Cost Analysis

### Monthly Costs (100 Active Users)

| Service | Usage | Cost |
|---------|-------|------|
| **Gemini API** | ~2000 requests/month (20/user) | ₹20-40/month |
| **Nominatim** | Free (rate-limited) | ₹0 |
| **Open-Meteo** | Free | ₹0 |
| **Reddit JSON** | Free | ₹0 |
| **OpenStreetMap Tiles** | Free (CDN cached) | ₹0 |
| **Hosting (Vercel)** | Free tier | ₹0 |
| **Hosting (Railway)** | Free tier | ₹0 |

**Total**: ~₹20-40/month for 100 users (~₹0.20-0.40 per user)

### Gemini API Breakdown

**Model**: `gemini-2.5-flash` (free tier during preview)

Per-user session:
- Itinerary generation: 1-2 calls (~₹0.01-0.02)
- Chat refinements: 3-5 calls (~₹0.03-0.05)
- City recommendations: 1 call (~₹0.01)
- Travel tips: 1 call cached (~₹0.01, one-time per destination)

**Average cost per session**: ₹0.10-0.15

---

## Performance Benchmarks

### API Response Times (P95)

| Endpoint | Response Time |
|----------|---------------|
| `/api/generate-itinerary` | 30-60s (streaming) |
| `/api/chat-refine` | 2-5s |
| `/api/recommend-cities` | 3-6s |
| `/api/travel-tips` (cached) | <200ms |
| `/api/travel-tips` (uncached) | 2-4s |
| `/api/geocode` | 500-1000ms |
| `/api/best-time` | 1-2s |

### Frontend Performance

- **Time to Interactive**: <3s
- **Largest Contentful Paint**: <2s
- **Cumulative Layout Shift**: <0.1
- **Bundle Size**: ~400KB (gzipped)

---

## Security & Privacy

### Data Handling

1. **No User Accounts**: Session-based, no authentication
2. **No Storage**: All data in-memory, lost on page refresh
3. **API Keys**: Server-side only, never exposed to frontend
4. **CORS**: Restricted to allowed origins
5. **Rate Limiting**: Nominatim and Reddit APIs rate-limited

### Content Filtering

- Profanity filter on all LLM outputs (`better-profanity`)
- Reddit content minimum score threshold
- YouTube content: search queries only (no direct embeds from user input)

---

## Known Limitations

1. **Qdrant In-Memory**: Data lost on API restart (Reddit/Wikivoyage content)
2. **No Persistent Storage**: Itineraries not saved
3. **Reddit Blocking**: Gemini fallback when Reddit returns 403
4. **Voice Support**: Browser-dependent (best on Chrome/Edge)
5. **Mobile**: Desktop-first (responsive on tablets, limited mobile UX)

---

## Future Enhancements

1. **Persistent Storage**: PostgreSQL for saved itineraries
2. **User Accounts**: Save/share trips
3. **Live Pricing**: Skyscanner/Amadeus APIs for flights
4. **Calendar Sync**: Google Calendar integration
5. **Mobile App**: React Native version with Anya
6. **Multilingual**: Support for Hindi, Spanish, French

---

## Recent Updates

### v3.0 — June 24, 2026 (Logo · SEO · Gemini 2.5 · UX Fixes)
- **Logo redesign**: Geometric gold W with diamond intersection nodes and compass arrow. Luxury brand aesthetic. Dual-tone gold for light/dark modes.
- **Gemini 2.5 Flash**: Upgraded from deprecated 2.0 Flash. 5-attempt retry with exponential backoff and 3-model fallback chain.
- **ThemeToggle fix**: MutationObserver-based toggle; eliminated stale-closure bug.
- **SEO/SEM**: Comprehensive JSON-LD structured data (Organization, WebSite, WebApplication, FAQPage). 20-keyword metadata. Open Graph + Twitter Card. Crawlable FAQ section.
- **Landing page redesign**: Sticky branded nav, card-style example trip chips, hero above fold.
- **Progress bar**: Sky-blue gradient fill (`#0EA5E9 → #38bdf8`) with glow.
- **CounterCard contrast**: Explicit Tailwind tokens replace CSS vars that resolved incorrectly in dark mode.
- **City names in English**: Nominatim `Accept-Language: en` + namedetails priority logic.
- **Comparison view**: Expanded from 3 to 10 qualitative parameters.
- **Column layout**: Left column cleaned (removed Visa/eSIM/Activities); "Book this trip" moved to right column.

### v2.1 — Design Revamp & Enhanced UX (June 2026)

**Design System Overhaul:**
- ✅ Travel-inspired color palette (Passport Navy, Horizon Amber, Map Ivory)
- ✅ Custom typography trio: Space Grotesk (display with wonky axis), DM Sans (body), JetBrains Mono (data)
- ✅ Signature ListeningOrb component with breathing animation
- ✅ StampChip component with vintage travel stamp aesthetic
- ✅ Updated layout proportions: 25% | 50% | 25%
- ✅ Map Ivory background with inset shadows

**New Features:**
- ✅ **FloatingAnyaButton**: Persistent voice access point on itinerary page (always visible)
- ✅ **Multi-city selection**: Users can add multiple cities when exploring a country
- ✅ **Duration question**: Suggest flow now asks for trip length before destination
- ✅ **YouTube thumbnails**: Travel tips cards display video thumbnails (128px, lazy-loaded)
- ✅ **Fallback travel tips**: Curated generic tips when Reddit/Gemini APIs fail

**Bug Fixes:**
- ✅ Fixed: Listening Orb disappearing after itinerary generation (now always accessible via FloatingAnyaButton)
- ✅ Fixed: Multi-destination flow not allowing multiple cities (added multi-city-confirm substage)
- ✅ Fixed: Suggest flow missing duration question (added DURATION_CHIPS: 3/5/7/10/14 days + Flexible)
- ✅ Fixed: Travel tips API returning empty results (added debug logging + fallback content)
- ✅ Fixed: YouTube thumbnails not displayed (integrated /api/youtube-thumbnail in Column3Sidebar)

**Technical Improvements:**
- Enhanced `ConversationalWizard` flow with `destinationSubStage` tracking
- Added `duration_days` field to `TripDates` interface
- Improved `travel_tips.py` with fallback templates and error logging
- Updated `TravelTip` interface with `thumbnailUrl` field

---

**Last Updated**: June 24, 2026  
**Maintained By**: WanderPlan Engineering
