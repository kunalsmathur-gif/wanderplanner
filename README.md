# WanderPlan

> Desktop-first AI travel advisor — plan group trips with AI-powered, personalized itineraries. No sign-up required.

[![Next.js](https://img.shields.io/badge/Next.js-14-black)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## What It Does

WanderPlan consolidates destination discovery, side-by-side location comparisons, AI-generated itinerary building, and post-selection logistics into a single desktop interface.

You describe your trip — who's coming, what you like, how much you have — and WanderPlan produces a timestamped, day-by-day schedule grounded in real traveler content from Reddit and Wikivoyage, with maps, YouTube travel guides, and booking deep-links all in one place.

**No API keys needed. No login. No subscriptions.**

---

## Features (Phase 1)

| Epic | Feature |
|---|---|
| **Onboarding Wizard** | Multi-step trip configuration: purpose, dates, personas, group composition, budget, accommodation preferences |
| **AI Itinerary Engine** | LLM-generated day-by-day schedule with timestamped routing, persona-gated work/fitness blocks, kid safety filtering, and social trend signals from Reddit |
| **Dual-Location Comparison** | Side-by-side grid comparing two destinations across budget, visa friction, travel time, kid/pet suitability, and weather |
| **Best Time to Travel** | Visual analytics: historical weather, busy tourist periods, seasonal cost index, local events calendar |
| **Ancillary Dashboard** | Visa advisory, flight/hotel booking redirects, live currency converter, packing checklist, safety notes |
| **PDF Export** | Download your full itinerary as a PDF — no account needed |

---

## Tech Stack

### Frontend (`/apps/web`)
| Technology | Purpose |
|---|---|
| Next.js 14 (App Router) + TypeScript | Framework, SSR, API proxy routes |
| Tailwind CSS + shadcn/ui | Design system (Horizon Blue / Emerald / Amber Gold tokens) |
| Zustand | Wizard + session state management |
| react-leaflet + OpenStreetMap | Interactive maps, scroll-synced itinerary pins |
| react-pdf | Client-side PDF itinerary export |
| Axios | HTTP client with error interceptors |

### Backend (`/apps/api`)
| Technology | Purpose |
|---|---|
| Python 3.11 + FastAPI | Async REST API, Pydantic validation, OpenAPI docs |
| LangChain + Groq (Llama 3.1 70B) | LLM orchestration, itinerary generation |
| Qdrant | Vector database for semantic travel content search |
| sentence-transformers (all-MiniLM-L6-v2) | Local text embeddings — no API key |
| BeautifulSoup4 + httpx | Wikivoyage, Wikipedia, OpenStreetMap scraping |
| Open-Meteo | Weather data (free, no key) |
| APScheduler | Scheduled Reddit content refresh |
| better-profanity | Safe content filtering |

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
│  Next.js 14 — 3-column layout (20% | 55% | 25%)             │
│  Zustand session state │ react-leaflet │ react-pdf           │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS
┌────────────────────────▼────────────────────────────────────┐
│              FastAPI (Railway)                               │
│  /generate-itinerary  /compare  /search  /best-time         │
│  LangChain → Groq (Llama 3.1 70B)                           │
│  Qdrant semantic search                                      │
│  APScheduler ingestion jobs                                  │
└───────┬───────────┬──────────────┬──────────────┬───────────┘
        │           │              │              │
   ┌────▼────┐ ┌────▼────┐  ┌─────▼─────┐  ┌────▼────────┐
   │  Qdrant  │ │  Groq   │  │  OSM /    │  │ Wikivoyage  │
   │ (vector  │ │  API    │  │ Open-Meteo│  │ Wikipedia   │
   │   DB)   │ │ (LLM)   │  │ Nominatim │  │ Reddit JSON │
   └─────────┘ └─────────┘  └───────────┘  └─────────────┘
```

---

## Getting Started (Local Development)

### Prerequisites

- **Node.js** 20+ and **npm** 10+
- **Python** 3.11+
- **Docker** and **Docker Compose** v2+
- A free [Groq API key](https://console.groq.com) (free tier, no credit card)

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

Edit `apps/api/.env` and set your `GROQ_API_KEY`.  
See the [Environment Variables](#environment-variables) section for all variables.

### 3. Start all services with Docker Compose

```bash
docker-compose up
```

This starts:
- **`api`** — FastAPI on `http://localhost:8000`
- **`qdrant`** — Vector DB on `http://localhost:6333`

### 4. Start the frontend development server

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:3000` in your browser.

> **Tip:** On first run, the backend will populate the Qdrant collections by scraping Wikivoyage and Reddit. This takes 2–5 minutes. The `/health` endpoint returns `{"status": "ready"}` when ingestion is complete.

### 5. (Optional) Use Ollama for local LLM during development

To avoid consuming Groq free-tier quota during development:

```bash
# Install Ollama: https://ollama.ai
ollama pull llama3.2
```

Then in `apps/api/.env`, set `LLM_PROVIDER=ollama`.

---

## Running Tests

### Backend

```bash
cd apps/api
pip install -r requirements-dev.txt
pytest                        # All unit + integration tests
pytest tests/unit/            # Unit tests only
pytest tests/integration/     # Requires Docker (Qdrant container)
```

### Frontend

```bash
cd apps/web
npm run test                  # Vitest unit + component tests
npm run test:e2e              # Playwright E2E (requires both servers running)
```

### Full CI suite (mirrors GitHub Actions)

```bash
# From repo root
npm run ci                    # Lint + type-check + all tests
```

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
| `GROQ_API_KEY` | Groq API key for Llama 3.1 70B inference | ✅ |
| `LLM_PROVIDER` | `groq` (default) or `ollama` | ❌ |
| `OLLAMA_BASE_URL` | Ollama server URL (default: `http://localhost:11434`) | ❌ |
| `QDRANT_URL` | Qdrant instance URL (default: `http://localhost:6333`) | ✅ |
| `QDRANT_API_KEY` | Qdrant API key (only needed for Qdrant Cloud; leave blank for self-hosted) | ❌ |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins (e.g., `http://localhost:3000`) | ✅ |
| `INGESTION_REFRESH_HOURS` | How often Reddit content is re-indexed (default: `6`) | ❌ |
| `CONTENT_FILTER_LEVEL` | `strict` or `moderate` (default: `strict`) | ❌ |

---

## Deployment

### Frontend → Vercel

1. Push your repo to GitHub
2. Import the repository in [Vercel](https://vercel.com/new)
3. Set **Root Directory** to `apps/web`
4. Add environment variables from the table above
5. Deploy — subsequent pushes to `main` auto-deploy

### Backend → Railway

1. Create a new Railway project
2. Add a **GitHub** service pointing to `/apps/api`
3. Add a **Qdrant** service (Railway template available) with a persistent volume
4. Set environment variables in Railway dashboard
5. Deploy

Full deployment guide: [`docs/deployment.md`](docs/deployment.md)

---

## Project Structure

```
wanderplan/
├── apps/
│   ├── web/                    # Next.js 14 frontend
│   │   ├── app/                # App Router pages and layouts
│   │   ├── components/         # UI components (wizard, itinerary, map, etc.)
│   │   ├── store/              # Zustand state stores
│   │   ├── lib/                # API client, utilities, PDF templates
│   │   └── public/             # Static assets
│   └── api/                    # FastAPI backend
│       ├── routers/            # FastAPI route handlers
│       ├── chains/             # LangChain chain definitions
│       ├── scrapers/           # Wikivoyage, Wikipedia, Reddit scrapers
│       ├── models/             # Pydantic request/response models
│       ├── services/           # Qdrant, Open-Meteo, Nominatim clients
│       └── tests/              # Pytest test suite
├── packages/
│   └── types/                  # Shared TypeScript + JSON Schema type definitions
├── docs/
│   ├── system-design.md        # Full system design document
│   └── deployment.md           # Step-by-step deployment guide
├── .github/
│   ├── workflows/              # GitHub Actions CI
│   └── ISSUE_TEMPLATE/         # Bug report template
├── docker-compose.yml
└── README.md
```

---

## Bug Reports

Found a bug? [Open a GitHub Issue](https://github.com/your-username/wanderplan/issues/new?template=bug_report.md).

Please include: steps to reproduce, expected vs. actual behavior, browser, OS, and a screenshot if possible.

---

## Roadmap

### Phase 1 (current)
- All 5 active Epics (Wizard, Itinerary Engine, Comparison, Best Time, Dashboard)
- No-API-key data stack
- Session-based, no login required

### Phase 2 (planned)
- Live flight pricing (Skyscanner/Amadeus API)
- Live hotel inventory (Booking.com API)
- Verified visa data (Sherpa API)
- Smart Calendar sync (Google Calendar, Outlook)
- Saved itineraries with user accounts

---

## License

MIT — see [LICENSE](LICENSE)
