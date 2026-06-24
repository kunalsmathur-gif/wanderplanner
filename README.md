# WanderPlan

> AI-powered travel planning with Anya, your conversational voice assistant. Desktop-first experience with personalized itineraries. No sign-up required.

[![Next.js](https://img.shields.io/badge/Next.js-16-black)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)](https://fastapi.tiangolo.com)
[![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash-4285F4)](https://ai.google.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## ✨ Meet Anya

**Anya** is your AI travel assistant — talk to her (literally!) to plan your trip. She asks questions, gives suggestions, and builds a complete itinerary tailored to you.

🎙️ **Voice Mode**: Click the voice button to have a natural conversation with Anya. She speaks with a young Indian female voice and listens to your responses.

---

## What It Does

WanderPlan uses conversational AI to help you plan trips through a natural chat interface. You tell Anya about your trip — who's coming, what you like, your budget — and she generates a day-by-day itinerary with:

- 📍 Timestamped activities with locations
- 🗺️ Interactive maps with route visualization
- 🌐 Community travel tips (Gemini-powered + Reddit)
- 🎥 YouTube video recommendations
- ✈️ Booking links (flights, hotels, activities)
- 💰 Budget breakdown and expense tracking
- 🌤️ Best time to visit recommendations

**Single-screen interface** with conversational chat overlay — everything in one place.

**No API keys needed. No login. No subscriptions.**

---

## Features

| Feature | Description |
|---|---|
| **🎙️ Anya Voice Assistant** | Conversational AI with voice input/output. Talk naturally to plan your trip. Young Indian female voice (20-25 yrs). Now with persistent floating orb for always-on access. |
| **💬 Chat Interface** | Full conversational wizard with quick-reply chips, city suggestions, multi-city support, and context-aware responses. |
| **🤖 AI Itinerary Engine** | Gemini 2.5 Flash generates day-by-day schedules with timestamped activities, routing, and budget allocation. Supports flexible trip durations. |
| **🗺️ Interactive Maps** | OpenStreetMap with itinerary pins, click-to-navigate, and route visualization. |
| **🌐 Travel Tips** | Gemini-powered community-style tips + Reddit highlights, with YouTube video thumbnails. Fallback curated tips ensure content is always available. |
| **📊 Destination Comparison** | Side-by-side grid comparing 10 qualitative parameters including budget, weather, visa friction, family fit, food scene, and overall suitability. |
| **🌤️ Best Time Widget** | Historical weather data, tourist seasons, and local events. |
| **✈️ Booking Integration** | Deep-links to Skyscanner, Booking.com, and Viator. |
| **💰 Budget Tracking** | Expense breakdown by category with currency conversion. |
| **📄 PDF Export** | Download your full itinerary — no account needed. |
| **🎨 Distinctive Design** | Geometric gold W brand mark with diamond nodes + compass arrow. Space Grotesk + DM Sans. Sky blue + adventure orange + ocean navy palette. Full dark/light mode. |

---

## Tech Stack

### Frontend (`/apps/web`)
| Technology | Purpose |
|---|---|
| Next.js 16 (Turbopack) + TypeScript | Framework, App Router, streaming, API routes |
| Tailwind CSS v4 | Modern utility-first styling with custom design tokens |
| Zustand | Lightweight state management (wizard, itinerary, config) |
| react-leaflet + OpenStreetMap | Interactive maps with activity pins |
| Web Speech API | Voice input (speech-to-text) |
| Speech Synthesis API | Voice output (text-to-speech) |
| Space Grotesk, DM Sans, JetBrains Mono | Custom font trio: display (wonky axis), body (tight tracking), data |
| Axios | HTTP client |

### Backend (`/apps/api`)
| Technology | Purpose |
|---|---|
| Python 3.9+ + FastAPI | Async REST API, Pydantic validation |
| Google Gemini 2.5 Flash | LLM for itinerary generation, chat, city recommendations |
| Qdrant (in-memory) | Vector database for semantic search |
| sentence-transformers | Local text embeddings (all-MiniLM-L6-v2) |
| httpx + BeautifulSoup4 | Web scraping (Wikivoyage, Reddit, YouTube) |
| Open-Meteo API | Historical weather data (free, no key) |
| APScheduler | Background jobs (Reddit content refresh) |

### Infrastructure
| Service | Role |
|---|---|
| Vercel | Frontend hosting (auto-deploy on push to `main`) |
| Railway | Backend (FastAPI + Qdrant with persistent volume) |
| Docker + docker-compose | Local dev orchestration |
| GitHub Actions | CI: lint, type-check, tests on every PR |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (Desktop)                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │    Anya - Conversational Wizard (Overlay)            │  │
│  │    🎙️ Voice Mode | 💬 Chat Interface               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Next.js 16 — 3-column layout (20% | 55% | 25%)            │
│  Zustand state | react-leaflet | Speech APIs                │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS
┌────────────────────────▼────────────────────────────────────┐
│              FastAPI (Python 3.9+)                           │
│  /api/generate-itinerary  /api/chat-refine                  │
│  /api/recommend-cities    /api/travel-tips                  │
│  Gemini 2.5 Flash | Qdrant | APScheduler                   │
└───────┬───────────┬──────────────┬──────────────┬───────────┘
        │           │              │              │
   ┌────▼────┐ ┌────▼────┐  ┌─────▼─────┐  ┌────▼────────┐
   │ Qdrant  │ │ Gemini  │  │ Open-Meteo│  │ Reddit JSON │
   │ (vector │ │ 2.5     │  │ Nominatim │  │ YouTube     │
   │   DB)   │ │ Flash   │  │    OSM    │  │ Wikivoyage  │
   └─────────┘ └─────────┘  └───────────┘  └─────────────┘
```

---

## Getting Started (Local Development)

### Prerequisites

- **Node.js** 20+ and **npm** 10+
- **Python** 3.9+
- A free [Google Gemini API key](https://aistudio.google.com/app/apikey)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/wanderplan.git
cd wanderplan
```

### 2. Configure environment variables

```bash
# Frontend
cp apps/web/.env.example apps/web/.env.local

# Backend
cp apps/api/.env.example apps/api/.env
```

Edit `apps/api/.env` and set your `GEMINI_API_KEY`.  
See the [Technical Documentation](TECHNICAL_DOCUMENTATION.md) for all variables.

### 3. Start the backend

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. Start the frontend development server

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:3000` in your browser.

**🎙️ Voice Mode**: Click the animated microphone button to talk with Anya!

> **Note:** On first run, the backend populates Qdrant with Reddit/Wikivoyage content (2-3 minutes). The `/health` endpoint returns `{"status": "ready"}` when complete.

---

## Documentation

- **[Technical Documentation](TECHNICAL_DOCUMENTATION.md)** — Complete tech stack, APIs, models, and architecture
- **[System Design](docs/system-design.md)** — Detailed system design document

---

## Environment Variables

### Frontend (`apps/web/.env.local`)

| Variable | Description | Required |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Backend FastAPI base URL | ✅ |
| `NEXT_PUBLIC_MAPTILER_KEY` | MapTiler key for OSM tile styling (optional — default tiles work without this) | ❌ |

### Backend (`apps/api/.env`)

| Variable | Description | Required |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API key | ✅ |
| `LLM_PROVIDER` | `gemini` (default) or `mock` | ❌ |
| `GEMINI_MODEL` | Model ID (default: `gemini-2.5-flash`) | ❌ |
| `QDRANT_URL` | Qdrant instance (default: `:memory:`) | ❌ |
| `ALLOWED_ORIGINS` | CORS origins (e.g., `http://localhost:3000`) | ✅ |

---

## Cost Analysis

**Monthly cost for 100 active users**: ~₹20-40 (~₹0.20-0.40 per user)

All external APIs are free except Gemini:
- **Gemini 2.5 Flash**: ~₹0.10-0.15 per session (itinerary + chat + tips)
- **Nominatim, Open-Meteo, Reddit, OSM**: Free
- **Vercel/Railway**: Free tiers sufficient for MVP

See [Technical Documentation](TECHNICAL_DOCUMENTATION.md#cost-analysis) for detailed breakdown.

---

## Roadmap

### Current (v2.1) — NEW: Design Revamp & Enhanced UX 🎨
- ✅ Conversational wizard with Anya
- ✅ Voice input/output (Indian English, young female)
- ✅ Single-screen interface with chat overlay
- ✅ Gemini 2.5 Flash for all LLM tasks
- ✅ Real-time travel tips with caching
- ✅ **NEW: Distinctive travel-inspired design system** (passport navy, horizon amber, vintage stamps)
- ✅ **NEW: Persistent floating Anya button** for always-on voice access
- ✅ **NEW: Multi-city selection** in exploring mode
- ✅ **NEW: Trip duration question** in suggest flow
- ✅ **NEW: YouTube thumbnails** for travel tips
- ✅ **NEW: Fallback curated tips** when APIs are unavailable

### Bug Fixes (v2.1)
- ✅ Fixed: Listening Orb now persistent across itinerary page
- ✅ Fixed: Multi-destination flow allows multiple cities
- ✅ Fixed: Suggest flow asks for trip duration before destination
- ✅ Fixed: Travel tips API with fallback content
- ✅ Fixed: YouTube thumbnails display in tip cards

### Next (v2.2)
- User accounts & saved itineraries
- Mobile-responsive redesign
- Multilingual support (Hindi, Spanish)
- Calendar sync (Google Calendar)
- Live flight pricing (Skyscanner API)

---

## License

MIT — see [LICENSE](LICENSE)
