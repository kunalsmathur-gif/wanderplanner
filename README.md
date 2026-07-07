# WanderPlanner

> AI-powered travel planning with Anya, your conversational AI concierge. Free sign-up via Google SSO or email/password — then plan freely.

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

WanderPlanner uses conversational AI to help you plan trips through a natural chat interface. Tell Anya about your trip — who's coming, what you like, your budget — and she generates a day-by-day itinerary with:

- 📍 Timestamped activities with locations
- 🗺️ Interactive maps with full-screen mode
- 🌐 Community travel tips (Reddit + Wikivoyage + AI-generated)
- 🎥 YouTube video recommendations per activity
- ✈️ Deep-links to Skyscanner, Booking.com, Viator
- 💰 Budget breakdown and live currency conversion
- 📄 Scrapbook-style PDF export with colorful day cards and destination photos
- 🌤️ Best time to visit with historical weather
- 📤 Shareable trip link (`/t/abc123`)
- 🗂️ Booking hub — track confirmation numbers, dates, amounts

**Free account. Google SSO or email/password. No subscription required.**

---

## Features

| Feature | Description |
|---|---|
| **🤖 LLM-Powered Anya Wizard** | Gemini 2.5 Flash drives the wizard — natural freeform conversation in English or Hinglish. One message fills multiple fields. Smart extraction: "yaar Bali trip 7 days, budget 1.5 lakh types" sets destination + dates + budget at once. Naming several places (e.g. "Colombo, Mirissa, and Yala") splits into a primary destination + hops; naming a whole country resolves to real cities the moment they're proposed/confirmed. Assistant history is replayed as structured JSON, invalid/truncated wizard responses are retried automatically, leaked schema/JSON tails are stripped before fallback text is shown, Stage-2 optional follow-ups stay interactive until the backend explicitly signals readiness, and theme chips reliably support multi-select submission via an explicit backend signal (not frontend guesswork). Reopening the wizard via "Edit Trip" on an existing itinerary carries the current trip forward instead of restarting the conversation. |
| **🔐 Free Account + Auth Gate** | Itinerary generation now requires a free account. Users can sign up with email/password or Google SSO; if they hit Generate while signed out, the frontend saves the collected trip config, redirects to `/signup?returnTo=/`, and auto-resumes generation after authentication. A shared `UserMenu` nav control shows "Log in/Sign up" when signed out, or your name/email + a "Log out" option when signed in — visible on the landing page, itinerary dashboard, and top nav. |
| **🔑 Password Reset** | Forgot/reset password flow with single-use reset links delivered by Resend. Resetting a password invalidates all existing refresh-token sessions defensively. |
| **✅ Consent + Legal Pages** | Signup requires a minimized consent checkbox linking to `/terms` and `/privacy`, with consent timestamped per account for DPDP-aligned recordkeeping. |
| **🗑️ Self-Service Account Deletion** | `/account` includes a danger-zone flow that requires typing `DELETE` before permanently removing the account and revoking refresh-token sessions. |
| **📈 Admin Analytics Dashboard** | Backend admin metrics endpoints summarize signups, sessions, logins, itinerary generation, and analytics events. Frontend dashboard UI is still in progress, but the backend data model and endpoints are live. |
| **🎙️ Anya Voice Assistant** | Conversational AI with voice input/output. Talk naturally to plan your trip. Young Indian female voice (20-25 yrs). |
| **💬 Persistent Anya Chat** | After itinerary generation, the floating Anya orb opens a slide-in chat panel. Ask questions, request changes — Anya patches config or offers to regenerate. |
| **📱 Mobile-Responsive** | Bottom tab navigation on mobile (Itinerary · Overview · Map & Tips). Full desktop 3-column layout on larger screens. |
| **🤖 AI Itinerary Engine** | Gemini 2.5 Flash generates day-by-day schedules with timestamped activities, routing, and budget allocation. 5-attempt retry + 3-tier RAG-powered fallback (cache → OSM skeleton → mock). RAG-grounded: hybrid BM25+semantic Qdrant retrieval (3 query variants w/ HyDE, RRF merge, cross-encoder rerank on the primary generation path) + time-decay + Jaccard dedup compressed to ~600 tokens. |
| **🗺️ Interactive Maps** | OpenStreetMap with activity pins. Full-screen map mode with day-tab navigation. |
| **🎴 Rich Activity Cards** | Compact `PolaroidCard` components — small thumbnail + text side-by-side (Wikipedia photo or YouTube thumbnail with hover zoom and link overlay), with automatic thumbnail retry and gradient-placeholder fallback if a lookup or image fails. |
| **🌐 Travel Tips** | Gemini-powered tips + Reddit highlights with YouTube thumbnails. |
| **📊 Destination Comparison** | Side-by-side AI comparison across 10 parameters: budget, weather, visa, family fit, food, romance, etc. |
| **🌤️ Best Time Widget** | Historical weather data, tourist seasons, local events. |
| **📤 Share Trip Link** | One-click generates a `/t/[slug]` read-only URL to share with travel companions. |
| **🚀 Start Anywhere** | Paste a blog post URL, Reddit thread, or trip notes — Anya extracts destination + days and pre-fills the wizard. |
| **🎨 Inspiration Gallery** | 12 curated trip starters with real Wikipedia photos on the landing page. Click any card to pre-fill the wizard with destination and days. |
| **🗂️ Booking Hub** | Track flights, hotels, activities, and transport — confirmation number, date, amount. Persists in localStorage. |
| **💰 Budget Tracking** | Expense breakdown by category with currency conversion widget. |
| **📄 PDF Export** | Download a colorful travel-journal PDF with per-day hero photos, booking link chips, transit warnings, and matching cards for essentials, visa/safety, cost breakdown, and packing checklist. |
| **🎨 Design System** | Geometric gold W brand mark. Space Grotesk + DM Sans + JetBrains Mono. Full dark/light mode with CSS custom properties — the toggle is reachable from the itinerary dashboard header, the persistent Anya chat panel, and the shared read-only trip link. |

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
| PostgreSQL + Supabase | Production transactional database for users, consent, sessions, analytics, and password resets |
| SQLAlchemy 2.0 async ORM + Alembic | Async database access and schema migrations (`0001_auth_analytics`, `0002_password_reset`) |
| Argon2id | Password hashing (`argon2-cffi`) |
| JWT + rotating refresh tokens | Cookie-based auth sessions (`wp_access_token`, `wp_refresh_token`) |
| Google OAuth 2.0 | Stateless Authorization Code flow for Google SSO |
| Resend | Transactional email delivery for password reset links |
| Qdrant (in-memory) | Vector database — 4 collections: `wiki`, `reddit`, `osm_pois`, `itinerary_cache` |
| sentence-transformers | Local text embeddings (all-MiniLM-L6-v2, 384 dims) + cross-encoder reranking (ms-marco-MiniLM-L-6-v2) |
| rank_bm25 | Lexical (BM25) retrieval, fused with semantic search via Reciprocal Rank Fusion |
| httpx | Async HTTP client (URL fetching for Start Anywhere, Overpass API POI queries) |
| BeautifulSoup4 | HTML parsing (Wikivoyage, Reddit) |
| Open-Meteo API | Historical weather data (free, no key) |
| Pexels API | Optional destination/activity stock photos for itinerary day cards in exported PDFs |
| APScheduler | Background jobs (Reddit refresh every 6h, OSM POI refresh weekly) |

### Infrastructure
| Service | Role |
|---|---|
| Vercel | Frontend hosting (auto-deploy on push to `main`) |
| Railway | Backend (FastAPI + Qdrant, persistent volume) |
| Supabase | Managed Postgres for production auth / analytics data |
| Docker + docker-compose | Local dev orchestration |
| GitHub Actions | CI: lint, type-check, tests on every PR |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (Desktop)                        │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Next.js 16 — landing + auth pages + 3-column itinerary   │  │
│  │                                                           │  │
│  │  /signup /login /forgot-password /reset-password         │  │
│  │  /account /terms /privacy                                │  │
│  │                                                           │  │
│  │  LLMWizard checks auth before generation:                 │  │
│  │   signed out → save pending config to sessionStorage      │  │
│  │             → redirect to /signup?returnTo=/             │  │
│  │   signed in  → stream itinerary normally                  │  │
│  └───────────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS / JSON / SSE / cookies
┌───────────────────────────▼─────────────────────────────────────┐
│                   FastAPI (Python 3.9+) Port 8000              │
│                                                                 │
│  Auth/session layer                                             │
│  POST /api/auth/signup|login    → email/password auth          │
│  GET  /api/auth/google/*        → Google OAuth round-trip      │
│  POST /api/auth/refresh         → rotate refresh token         │
│  POST /api/auth/password/*      → forgot/reset password        │
│                                                                 │
│  Product/API layer                                               │
│  POST /api/generate-itinerary  → requires get_current_user     │
│  POST /api/chat-refine         → Anya persistent chat handler  │
│  POST /api/recommend-cities    → City suggestions (Gemini)     │
│  POST /api/extract-trip        → URL/text → trip fields        │
│  GET  /api/admin/metrics/*     → admin analytics summaries     │
│  POST /api/analytics/client-event → client-side analytics      │
│                                                                 │
│  Background: Reddit refresh every 6h · OSM POI refresh weekly  │
│              Qdrant retrieval + Postgres-backed auth/analytics │
└──────┬──────────────┬────────────────┬───────────────┬──────────┘
       │              │                │               │
┌──────▼──────┐ ┌─────▼──────┐  ┌─────▼──────┐ ┌──────▼─────────────────┐
│   Qdrant    │ │   Gemini   │  │ Supabase   │ │ External APIs           │
│ (in-memory) │ │  2.5 Flash │  │ Postgres   │ │ Google OAuth · Resend   │
│ wiki+reddit │ │ lite/1.5   │  │ users      │ │ Nominatim · Open-Meteo  │
│ osm_pois+   │ │ fallbacks  │  │ sessions    │ │ Reddit JSON · YouTube   │
│ itin_cache  │ │            │  │ analytics   │ │ Overpass · Wikipedia    │
└─────────────┘ └────────────┘  └────────────┘ └─────────────────────────┘
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

Edit `apps/api/.env` and set at least:

- `GEMINI_API_KEY`
- `DATABASE_URL`
- `JWT_SECRET`
- `FRONTEND_BASE_URL`

If you want Google SSO, add the `GOOGLE_*` variables. If you want password reset, add `RESEND_API_KEY` + `EMAIL_FROM_ADDRESS`. `PEXELS_API_KEY` remains optional for itinerary day photos in exported PDFs.

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
| `DATABASE_URL` | Postgres connection string (local Postgres or Supabase) | ✅ |
| `JWT_SECRET` | Secret used to sign access tokens and auth state | ✅ |
| `ACCESS_TOKEN_TTL_MINUTES` | Access-token lifetime (default: 15) | ❌ |
| `REFRESH_TOKEN_TTL_DAYS` | Refresh-token lifetime (default: 30) | ❌ |
| `COOKIE_DOMAIN` | Optional cookie domain override | ❌ |
| `COOKIE_SECURE` | `true` in production; may be `false` for local HTTP dev | ❌ |
| `COOKIE_SAMESITE` | `lax` for local dev, `none` for cross-origin prod | ❌ |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | ✅ for Google SSO |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | ✅ for Google SSO |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL (e.g. `http://localhost:8000/api/auth/google/callback`) | ✅ for Google SSO |
| `FRONTEND_BASE_URL` | Frontend origin for redirects and reset links | ✅ |
| `RESEND_API_KEY` | Resend API key for password-reset email | ✅ for password reset |
| `EMAIL_FROM_ADDRESS` | From-address used by Resend | ✅ for password reset |
| `PASSWORD_RESET_TOKEN_TTL_MINUTES` | Reset-link TTL (default: 30) | ❌ |
| `QDRANT_URL` | Qdrant instance URL (default: `:memory:`) | ❌ |
| `PEXELS_API_KEY` | Optional Pexels API key for itinerary day photos in exported PDFs | ❌ |
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

### v5.6 — Local Testing Fixes: Auth Nav Indicator, Wizard Resume Race, Chip Backfill (July 2026)
- ✅ **FIXED: no way to tell if you're signed in** — the home page had no login/signup CTA, no indicator of an active session, and no discoverable sign-out option outside of `/account`. Added a shared `UserMenu` component (Log in/Sign up when signed out; name/email + Log out dropdown when signed in), wired into the landing page nav, the itinerary dashboard title bar, and the top nav bar.
- ✅ **FIXED: wizard losing/duplicating context after sign-in** — a mount-effect race in `LLMWizard.tsx` could inject a stray fresh greeting on top of a resumed generation right after completing signup mid-wizard. Fixed with a single shared snapshot of the pending-generation flag plus a resume idempotency guard.
- ✅ **FIXED: missing trip-type chips on Anya's first message** — added a deterministic server-side backfill so the standard purpose chips (Leisure/Adventure/Honeymoon/etc.) always appear on turn one, even on the rare occasion Gemini's response omits them.
- ✅ **FIXED: SQLite FK cascades silently no-op'ing during local testing** — `apps/api/db.py` now enables `PRAGMA foreign_keys=ON` for SQLite connections only; zero effect on the Postgres/Supabase production path.
- ✅ Verified: 113 backend + 36 frontend automated tests pass; all four fixes additionally confirmed live against running local dev servers.

### v5.5 — Accounts, Auth Gate, Password Reset & Admin Analytics (July 2026)
- ✅ Added **Postgres-backed auth + analytics** with async SQLAlchemy 2.0 ORM, Alembic migrations, and **Supabase** as the production Postgres host.
- ✅ Added **free accounts** via email/password or **Google SSO**, plus cookie-based JWT + rotating refresh-token sessions.
- ✅ Added **forgot/reset password**, **consent capture**, `/terms` + `/privacy`, and self-service `/account` deletion.
- ✅ Moved **itinerary generation behind server-side auth**; the frontend now preserves a pending trip config through the sign-in round-trip and auto-resumes generation afterward.
- ✅ Added **admin analytics endpoints** plus a generic events table for sessions, logins, itinerary outcomes, and future Gemini/Pexels usage tracking.

### v5.4 — WanderPlanner Rebrand + Wizard/UI Reliability Fixes (July 2026)
- ✅ **Rebrand: WanderPlan → WanderPlanner** across every UI string, backend module, doc, and asset — no functional change.
- ✅ **FIXED: multi-city trips dropped by Anya** — naming several places in one message (e.g. "Colombo, Mirissa, and Yala National Park") now correctly splits into a primary destination + hops instead of silently keeping only the first city.
- ✅ **FIXED: country-mode trips never resolved to a real city** — naming a whole country (e.g. "Italy") now resolves to concrete cities the instant Anya proposes or the user confirms them, instead of leaving budget/booking/travel-tips panels blank.
- ✅ **FIXED: blank budget/booking/tips panels** for country-mode and Anya-driven trips — `Column1Metrics`/`Column3Sidebar` now fall back to the destination country and show a "City +N" label for multi-hop trips.
- ✅ **REDESIGNED: activity cards** — `PolaroidCard` rebuilt from an oversized full-width 16:9 video hero into a compact horizontal thumbnail+text layout so the itinerary is scannable at a glance.
- ✅ **FIXED: intermittent missing YouTube thumbnails** — retry up to 3x with backoff, only cache successful lookups (never poison a query on a transient failure), and gracefully fall back to a placeholder if an image later 404s.
- ✅ **FIXED: theme multiselect regression** — chip multi-select is now driven by an explicit backend `multi_select` signal instead of a frontend keyword guess that could misfire when Gemini varied chip wording.
- ✅ **NEW: dark/light toggle** on the itinerary dashboard and the persistent Anya chat panel (previously only on the shared trip link page).
- ✅ **FIXED: "Edit Trip" losing all context** — reopening the wizard on an already-generated itinerary now carries the existing trip config forward and offers targeted "change X" chips instead of restarting the whole conversation.

### v5.3 — RAG Optimization Round 2 (July 2026)
- ✅ **NEW: Hybrid BM25 + semantic search** — lexical BM25 (destination-scoped Qdrant scroll) fused with semantic cosine search via RRF on every retrieval call. Fixes proper-noun confusion (e.g. Tokyo vs Kyoto).
- ✅ **NEW: HyDE query augmentation** — template-based hypothetical travel-guide passage synthesized and embedded for the "vibe" query variant, no extra LLM call.
- ✅ **NEW: Cross-encoder reranking (scoped)** — `ms-marco-MiniLM-L-6-v2` reranks the primary itinerary-generation retrieval path only (disabled by default elsewhere due to latency cost).
- ✅ **NEW: OSM POI ingestion** — `scrapers/osm.py` fetches real POIs (name, category, lat/lon) from the free Overpass API, weekly scheduled refresh, feeds the new `osm_pois` Qdrant collection.
- ✅ **NEW: Itinerary cache + 3-tier RAG fallback** — successful itineraries cached (`itinerary_cache` collection); on LLM failure, falls through cache hit → OSM-grounded skeleton → RAG-tipped enhanced mock instead of a hard error.
- ✅ **FIXED: RAG retrieval concurrency bug** — blocking `embed()`/Qdrant calls previously serialized on the event loop despite `asyncio.gather()`; now correctly offloaded via `asyncio.to_thread()` + batched embedding. Throughput ~10 → ~23.6 req/s @ concurrency=50 (pre-hybrid/HyDE/rerank).
- ✅ **NEW: Golden dataset + automated retrieval eval** — `apps/api/eval/golden_dataset.json` + `run_rag_eval.py` compute Precision@k/Recall@k/MRR/nDCG@k.
- ✅ **NEW: RAG load test tool** — `apps/api/load_test_rag.py` measures retrieval throughput/latency under concurrency.

### v5.2 — RAG Pipeline Overhaul (June 2026)
- ✅ **NEW: Gemini path now RAG-grounded** — `_gemini_itinerary()` was silently bypassing `retrieve_context()`. All production itineraries now receive real traveller data from Qdrant.
- ✅ **NEW: Multi-query retrieval with RRF** — 3 parallel query variants (config / vibe / practical) merged via Reciprocal Rank Fusion (k=60). Better recall for niche trips and vibe searches.
- ✅ **NEW: Time-decay scoring** — exponential decay with 18-month half-life. A 3-year-old post at score 0.91 → 0.55. `published_date` stored in Reddit Qdrant payloads.
- ✅ **NEW: Context summarisation** — `summarise_context()` compresses 20 raw chunks (~7,500 tokens) to ~600 tokens via score filter, Jaccard dedup, and 2400-char budget. **87% token reduction**.
- ✅ **NEW: Sentence-boundary Wikivoyage chunking** — replaced hard 1500-char cuts with sentence-aware ~500-char chunks. Each section now produces N high-precision chunks.
- ✅ **NEW: Reddit paragraph chunking** — each post split at `\n\n` into paragraph chunks (≥80 chars), each prefixed with the title for standalone retrieval context.
- ✅ **NEW: Reddit destination tagging fixed** — `_extract_destination()` now uses word-boundary regex against 200+ destinations. Was always returning `"general"`.

### v5.0 — LLM Wizard + Mobile-Responsive (June 2026)
- ✅ **NEW: LLM-powered Anya wizard** — replaces scripted state machine. Gemini 2.5 Flash collects all trip fields through freeform conversation. One message can fill multiple fields ("just me and my wife for 7 days to Bali, budget ₹1L, moderate pace").
- ✅ **NEW: Mobile-responsive layout** — bottom tab bar (Itinerary · Overview · Map) on mobile; 3-column layout on desktop `lg+`
- ✅ **NEW: `/api/wizard-chat` endpoint** — new backend chain with Anya wizard system prompt, `config_patch` extraction, and server-side `ready_to_generate` validation
- ✅ **NEW: RAG context injection** — Reddit + Wikivoyage chunks retrieved via Qdrant and injected into every itinerary generation prompt

### v5.1 — Anya Prompt v3 + Bug Fixes (June 2026)
- Anya system prompt completely rewritten (v3): 9 structured sections, Indian cultural context, Hinglish/STT handling, currency parsing (25k/1L/lakh), travel season awareness, veg/Jain food sensitivity
- 3-stage conversation flow: collect fields → "anything else?" checkpoint → generate
- `thought_process` chain-of-thought field added to wizard responses (debug/logging)
- Fixed: bootstrap empty messages → Gemini "contents required" error
- Fixed: JSON fence parsing (regex-based, handles all code fence variants)
- Fixed: stale closure bug — partialConfigRef ensures latest config sent to backend
- Fixed: generate loop — "Generate itinerary" chip filtered; button shows on server ready signal
- Fixed: Gemini API errors fall back to mock instead of returning 500

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
