# WanderPlan

> AI-powered travel planning with Anya, your conversational AI concierge. Desktop-first, no sign-up, no cost.

[![Next.js](https://img.shields.io/badge/Next.js-16-black)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)](https://fastapi.tiangolo.com)
[![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash-4285F4)](https://ai.google.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## ✨ Meet Anya

**Anya** is your AI travel concierge — talk to her (literally!) to plan your trip. She asks questions, gives suggestions, builds a complete itinerary, and stays available after it's generated for real-time refinements.

🎙️ **Voice Mode**: Click the voice button to have a natural conversation with Anya.  
💬 **Persistent Chat**: After your itinerary is ready, Anya stays as a floating panel for follow-up questions and live adjustments.

---

## What It Does

WanderPlan uses conversational AI to help you plan trips through a natural chat interface. Tell Anya about your trip — who's coming, what you like, your budget — and she generates a day-by-day itinerary with:

- 📍 Timestamped activities with locations
- 🗺️ Interactive maps with full-screen mode
- 🌐 Community travel tips (Reddit + Wikivoyage + AI-generated)
- 🎥 YouTube video recommendations per activity
- ✈️ Deep-links to Skyscanner, Booking.com, Viator
- 💰 Budget breakdown and live currency conversion
- 🌤️ Best time to visit with historical weather
- 📤 Shareable trip link (`/t/abc123`)
- 🗂️ Booking hub — track confirmation numbers, dates, amounts

**No API keys. No login. No subscriptions.**

---

## Features

| Feature | Description |
|---|---|
| **🤖 LLM-Powered Anya Wizard** | Gemini 2.5 Flash drives the wizard — natural conversation collects all trip fields. One message fills multiple fields. Smart extraction: "just me and wife for 7 days ₹1L" sets group + dates + budget at once. |
| **🎙️ Anya Voice Assistant** | Conversational AI with voice input/output. Talk naturally to plan your trip. Young Indian female voice (20-25 yrs). |
| **💬 Persistent Anya Chat** | After itinerary generation, the floating Anya orb opens a slide-in chat panel. Ask questions, request changes — Anya patches config or offers to regenerate. |
| **📱 Mobile-Responsive** | Bottom tab navigation on mobile (Itinerary · Overview · Map & Tips). Full desktop 3-column layout on larger screens. |
| **🤖 AI Itinerary Engine** | Gemini 2.5 Flash generates day-by-day schedules with timestamped activities, routing, and budget allocation. 5-attempt retry + fallback chain. |
| **🗺️ Interactive Maps** | OpenStreetMap with activity pins. Full-screen map mode with day-tab navigation. |
| **🎴 Rich Activity Cards** | PolaroidCard components with Wikipedia photos, hover zoom, YouTube link overlay. |
| **🌐 Travel Tips** | Gemini-powered tips + Reddit highlights with YouTube thumbnails. |
| **📊 Destination Comparison** | Side-by-side AI comparison across 10 parameters: budget, weather, visa, family fit, food, romance, etc. |
| **🌤️ Best Time Widget** | Historical weather data, tourist seasons, local events. |
| **📤 Share Trip Link** | One-click generates a `/t/[slug]` read-only URL to share with travel companions. |
| **🚀 Start Anywhere** | Paste a blog post URL, Reddit thread, or trip notes — Anya extracts destination + days and pre-fills the wizard. |
| **🎨 Inspiration Gallery** | 12 curated trip starters with real Wikipedia photos on the landing page. Click any card to pre-fill the wizard with destination and days. |
| **🗂️ Booking Hub** | Track flights, hotels, activities, and transport — confirmation number, date, amount. Persists in localStorage. |
| **💰 Budget Tracking** | Expense breakdown by category with currency conversion widget. |
| **📄 PDF Export** | Download your full itinerary — no account needed. |
| **🎨 Design System** | Geometric gold W brand mark. Space Grotesk + DM Sans + JetBrains Mono. Full dark/light mode with CSS custom properties. |

---

## Tech Stack

### Frontend (`/apps/web`)
| Technology | Purpose |
|---|---|
| Next.js 16 (Turbopack) + TypeScript | Framework, App Router, streaming, RSC |
| Tailwind CSS v4 | Utility-first styling with CSS custom property design tokens |
| Zustand | State management — 6 stores (wizard, itinerary, config, app, chat, booking) |
| react-leaflet + OpenStreetMap | Interactive maps with activity pins |
| Web Speech API | Voice input (speech-to-text) |
| Speech Synthesis API | Voice output (text-to-speech) |
| Space Grotesk, DM Sans, JetBrains Mono | Display / body / data font trio |
| Axios | HTTP client |
| Wikipedia API | Free destination photos (no key, CORS-safe) |

### Backend (`/apps/api`)
| Technology | Purpose |
|---|---|
| Python 3.9+ + FastAPI | Async REST API, Pydantic v2 validation |
| Google Gemini 2.5 Flash | Itinerary gen, chat refine, city recommendations, trip extraction |
| Qdrant (in-memory) | Vector database for semantic travel content search |
| sentence-transformers | Local text embeddings (all-MiniLM-L6-v2, 384 dims) |
| httpx | Async HTTP client (URL fetching for Start Anywhere) |
| BeautifulSoup4 | HTML parsing (Wikivoyage, Reddit) |
| Open-Meteo API | Historical weather data (free, no key) |
| APScheduler | Background jobs (Reddit content refresh every 6h) |

### Infrastructure
| Service | Role |
|---|---|
| Vercel | Frontend hosting (auto-deploy on push to `main`) |
| Railway | Backend (FastAPI + Qdrant, persistent volume) |
| Docker + docker-compose | Local dev orchestration |
| GitHub Actions | CI: lint, type-check, tests on every PR |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (Desktop)                          │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Next.js 16 — 3-column layout (20% | 55% | 25%)            │ │
│  │                                                               │ │
│  │  ┌──────────┐  ┌──────────────────────┐  ┌───────────────┐ │ │
│  │  │ Column 1 │  │      Column 2         │  │   Column 3    │ │ │
│  │  │          │  │  Itinerary Timeline   │  │  Map (Leaflet)│ │ │
│  │  │ Metrics  │  │  PolaroidCard cards   │  │  Full-screen  │ │ │
│  │  │ Expenses │  │  Comparison Panel     │  │  map mode     │ │ │
│  │  │ Currency │  │  ShareButton header   │  │  Best Time    │ │ │
│  │  │ Booking  │  └──────────────────────┘  │  Travel Tips  │ │ │
│  │  │   Hub    │                             └───────────────┘ │ │
│  │  └──────────┘                                                │ │
│  │                                                               │ │
│  │  Floating: Anya Orb → ChatPanel (persistent post-gen chat)  │ │
│  │  Overlay: ConversationalWizard (full-screen on open)        │ │
│  │  LandingHero: Inspiration gallery + Start Anywhere input    │ │
│  │                                                               │ │
│  │  Zustand (6 stores): appStore · tripConfigStore             │ │
│  │  wizardChatStore · itineraryStore · chatStore · bookingStore│ │
│  └─────────────────────────────────────────────────────────────┘ │
└───────────────────────────┬─────────────────────────────────────┘
                             │ HTTPS / JSON / SSE
┌───────────────────────────▼─────────────────────────────────────┐
│                   FastAPI (Python 3.9+) Port 8000                 │
│                                                                    │
│  POST /api/generate-itinerary   → Gemini 2.5 Flash (5× retry)  │
│  POST /api/chat-refine          → Anya persistent chat handler  │
│  POST /api/recommend-cities     → City suggestions (Gemini)     │
│  POST /api/extract-trip         → URL/text → trip fields        │
│  POST /api/share                → Serialize trip → slug         │
│  GET  /api/share/{slug}         → Read-only trip data           │
│  GET  /api/travel-tips          → AI tips (cached 1h)           │
│  GET  /api/best-time/{city}     → Open-Meteo weather data       │
│  GET  /api/geocode              → Nominatim (en names, is_country)│
│  POST /api/compare-destinations → 10-param AI comparison        │
│  Background: Reddit refresh every 6h · Qdrant ingestion         │
└──────┬──────────────┬────────────────┬──────────────────────────┘
       │              │                │
┌──────▼──────┐ ┌─────▼──────┐  ┌─────▼──────────────────────────┐
│   Qdrant    │ │   Gemini   │  │  External APIs                  │
│ (in-memory) │ │  2.5 Flash │  │  Nominatim · Open-Meteo        │
│ reddit+wiki │ │ lite/1.5   │  │  Reddit JSON · YouTube         │
│ collections │ │ fallbacks  │  │  Wikipedia (frontend, CORS-safe)│
└─────────────┘ └────────────┘  └─────────────────────────────────┘
```

---

## Getting Started (Local Development)

### Prerequisites

- **Node.js** 20+ and **npm** 10+
- **Python** 3.9+
- A free [Google Gemini API key](https://aistudio.google.com/app/apikey)

### 1. Clone the repository

```bash
git clone https://github.com/kunalsmathur-gif/wanderplanner.git
cd wanderplanner
```

### 2. Configure environment variables

```bash
cp apps/web/.env.example apps/web/.env.local
cp apps/api/.env.example apps/api/.env
```

Edit `apps/api/.env` and set your `GEMINI_API_KEY`.

### 3. Start the backend

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Start the frontend

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:3000`.

> **First run**: The backend populates Qdrant with Reddit/Wikivoyage content (2-3 min). `/health` returns `{"status":"ready"}` when complete.

---

## Documentation

- **[Technical Documentation](TECHNICAL_DOCUMENTATION.md)** — Full tech stack, APIs, models, architecture
- **[System Design](docs/system-design.md)** — Detailed system design with data flows and API contracts

---

## Environment Variables

### Frontend (`apps/web/.env.local`)

| Variable | Description | Required |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Backend FastAPI base URL (e.g. `http://localhost:8000`) | ✅ |
| `NEXT_PUBLIC_MAPTILER_KEY` | MapTiler key for styled OSM tiles | ❌ |

### Backend (`apps/api/.env`)

| Variable | Description | Required |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API key | ✅ |
| `LLM_PROVIDER` | `gemini` (default) or `mock` | ❌ |
| `GEMINI_MODEL` | Model ID (default: `gemini-2.5-flash`) | ❌ |
| `QDRANT_URL` | Qdrant instance URL (default: `:memory:`) | ❌ |
| `ALLOWED_ORIGINS` | CORS origins (e.g. `http://localhost:3000`) | ✅ |

---

## Cost Analysis

**Monthly cost for 100 active users**: ~₹20–40 (~₹0.20–0.40/user)

| Service | Cost |
|---|---|
| Gemini 2.5 Flash | ~₹0.10–0.15 per session |
| Nominatim, Open-Meteo, Reddit, OSM, Wikipedia | Free |
| Vercel / Railway | Free tiers sufficient for MVP |

---

## Changelog

### v5.0 — LLM Wizard + Mobile-Responsive (June 2026)
- ✅ **NEW: LLM-powered Anya wizard** — replaces scripted state machine. Gemini 2.5 Flash collects all trip fields through freeform conversation. One message can fill multiple fields ("just me and my wife for 7 days to Bali, budget ₹1L, moderate pace").
- ✅ **NEW: Mobile-responsive layout** — bottom tab bar (Itinerary · Overview · Map) on mobile; 3-column layout on desktop `lg+`
- ✅ **NEW: `/api/wizard-chat` endpoint** — new backend chain with Anya wizard system prompt, `config_patch` extraction, and server-side `ready_to_generate` validation
- ✅ **NEW: RAG context injection** — Reddit + Wikivoyage chunks retrieved via Qdrant and injected into every itinerary generation prompt

### v3.0 — Competitor Parity Update (June 2026)
- ✅ **NEW: Persistent Anya chat panel** — floating orb opens slide-in chat after itinerary generation
- ✅ **NEW: Shareable trip link** — `/t/[slug]` read-only view; one-click copy via ShareButton
- ✅ **NEW: Start Anywhere** — paste any URL/blog/Reddit post; Gemini extracts destination + days
- ✅ **NEW: Booking Hub** — track flights, hotels, activities with confirmation numbers (localStorage persisted)
- ✅ **NEW: Inspiration gallery** — 12 curated trips with Wikipedia photos on landing page; click-to-preload wizard
- ✅ **NEW: Rich PolaroidCard activity cards** — Wikipedia photos, hover zoom, YouTube overlay
- ✅ **NEW: Full-screen map mode** — expand to full viewport with day-tab navigation
- ✅ **NEW: Visual destination cards** — photo cards with Wikipedia images in "Suggest me!" flow
- ✅ **NEW: Country auto-detection** — typing a country name in destination switches to multi-city mode
- ✅ **NEW: Wizard preload** — inspiration cards pre-fill destination + days in wizard
- ✅ Removed redundant example trip chips (replaced by Inspiration gallery)
- ✅ Nav anchor links (Inspiration, FAQ) in LandingHero sticky header

### v2.1 — Design Revamp (June 2026)
- ✅ Geometric gold W brand mark (SVG)
- ✅ Space Grotesk + DM Sans + JetBrains Mono font system
- ✅ Full dark/light mode with CSS custom properties
- ✅ Multi-city destination flow
- ✅ Gemini 2.5 Flash with 5-attempt retry + fallback chain
- ✅ Budget input overlap fix, right column scrollability fix

### Next (v3.1)
- Mobile-responsive redesign
- User accounts and saved itineraries
- Multilingual support (Hindi, Spanish)
- Calendar sync (Google Calendar)
- Live flight pricing (Skyscanner API)
- Email forwarding for booking confirmation parsing

---

## License

MIT — see [LICENSE](LICENSE)
