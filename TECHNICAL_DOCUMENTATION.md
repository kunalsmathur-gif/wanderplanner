# WanderPlanner — Technical Documentation

**Version:** 10.21.0 (UI/UX audit §2.1+§2.2: dark-mode token pass on six light-only components, plain-language error copy, dead WizardForm wizard deleted)
**Last Updated:** July 13, 2026  
**Status:** Production-ready MVP

---

## Table of Contents

1. [Overview](#1-overview)
2. [Tech Stack](#2-tech-stack)
3. [Design System](#3-design-system)
4. [Frontend Architecture](#4-frontend-architecture)
5. [State Management (Zustand)](#5-state-management-zustand)
6. [Backend Architecture](#6-backend-architecture)
6A. [Authentication & Session Management](#6a-authentication--session-management)
7. [API Reference](#7-api-reference)
7A. [Admin Analytics Dashboard](#7a-admin-analytics-dashboard)
8. [AI Models, Prompts & RAG](#8-ai-models-prompts--rag)
9. [Key Frontend Components](#9-key-frontend-components)
10. [Hooks & Utilities](#10-hooks--utilities)
11. [Voice Features](#11-voice-features)
12. [Data Flows](#12-data-flows)
13. [Environment Setup](#13-environment-setup)
14. [Recent Changes (v10.15 → v5.0)](#14-recent-changes-v1015-v1014-v1013-v1012-v1011-v1010-v109-v108-v107-v106-v105-v104-v103-v102-v101-v100-v90-v70-v60--v50)

---

## 1. Overview

WanderPlanner is an AI-powered travel planning platform. Users interact with **Anya**, a conversational AI concierge, to produce a complete day-by-day itinerary. Key differentiators vs competitors (Mindtrip, TripIt, Travaa):

| Dimension | WanderPlanner |
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
| **Dedicated auth pages** | — | `/signup`, `/login`, `/forgot-password`, `/reset-password`, `/account`, `/terms`, `/privacy` |
| **Session storage + cookies** | Native | Pending-generation resume across OAuth/full-page redirects; credentialed API calls |
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
| **PostgreSQL** | 16+ | Transactional data store for users, refresh tokens, password reset tokens, analytics events |
| **Supabase** | Managed | Production Postgres hosting |
| **SQLAlchemy 2.0** | Latest | Async ORM / session management |
| **Alembic** | Latest | Schema migrations (`0001_auth_analytics`, `0002_password_reset`) |
| **Argon2id** | Latest | Password hashing for email/password accounts |
| **JWT + rotating refresh tokens** | Custom | Cookie-based auth sessions (`wp_access_token`, `wp_refresh_token`) |
| **Google OAuth 2.0** | Latest | Stateless Authorization Code flow for Google SSO |
| **itsdangerous** | Latest | Signed stateless Google OAuth `state` parameter |
| **Resend** | Latest | Transactional email for password reset |
| **Google Generative AI** | Latest | Gemini API client |
| **Qdrant** | 1.x | Vector DB (in-memory mode) |
| **sentence-transformers** | - | Embeddings (all-MiniLM-L6-v2, 384 dims) |
| **httpx** | - | Async HTTP (URL fetch for Start Anywhere) |
| **BeautifulSoup4** | - | HTML parsing |
| **Pexels API** | Free tier | Optional destination/activity hero photos for itinerary days and PDF export |
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
│   ├── signup/page.tsx     — Email/password signup + consent + Google SSO
│   ├── login/page.tsx      — Login + Google SSO
│   ├── forgot-password/page.tsx — Forgot-password request page
│   ├── reset-password/page.tsx  — Password reset completion page
│   ├── account/page.tsx    — Authenticated profile + self-delete danger zone
│   ├── terms/page.tsx      — Terms of Service
│   ├── privacy/page.tsx    — Privacy Policy
│   └── t/[slug]/page.tsx   — Shareable read-only trip view
├── components/
│   ├── chat/
│   │   ├── ChatPanel.tsx   — Persistent Anya chat slide-in panel
│   │   ├── ChatMessage.tsx — Individual message bubble
│   │   └── ChatBubble.tsx
│   ├── common/
│   │   ├── LandingHero.tsx     — Landing: nav + hero + Start Anywhere + gallery + FAQ
│   │   ├── FloatingAnyaButton.tsx — Orb: opens ChatPanel (itinerary) or wizard (landing)
│   │   ├── AuthLayout.tsx      — Shared centered card shell for auth pages
│   │   ├── GoogleSignInButton.tsx — Google OAuth CTA
│   │   ├── AuthHydrator.tsx    — Session bootstrap + `session_start` analytics beacon
│   │   ├── ShareButton.tsx     — Generates /t/[slug] link, copies to clipboard
│   │   ├── WanderplannerLogo.tsx  — SVG geometric gold W
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
│   ├── pdf/
│   │   └── ItineraryDocument.tsx — @react-pdf/renderer export with scrapbook-style day cards
│   └── wizard/
│       ├── LLMWizard.tsx         — LLM-powered Anya wizard (replaces state machine)
│       └── ConversationalWizard.tsx — Legacy scripted wizard (kept for reference)
├── hooks/
│   └── useWikiImage.ts     — Shared Wikipedia photo hook (cached, CORS-safe)
├── store/                  — See Section 5
├── lib/
│   ├── api.ts              — Main backend API calls + credentialed itinerary SSE
│   ├── authApi.ts          — Auth-specific axios client (`withCredentials: true`)
│   └── pendingGeneration.ts — sessionStorage-backed pre-auth itinerary resume
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

The live wizard CTA is now derived from the backend's explicit Stage-3 ready signal (`summary !== null` / `ready_to_generate=true`), not from a frontend count of required fields. This keeps the text input visible during Stage 2 follow-up prompts such as departure-city or theme refinement.

### `authStore.ts`
Cookie-backed auth/session state.

```typescript
{
  user: AuthUser | null
  status: 'idle' | 'loading' | 'authenticated' | 'unauthenticated'
  hydrate(): Promise<void>
  login(email, password): Promise<AuthUser>
  signup(input): Promise<AuthUser>
  logout(): Promise<void>
}
```

`AuthHydrator.tsx` mounts in `app/layout.tsx`, calls `hydrate()` on boot, and emits a `session_start` analytics beacon. `LLMWizard.tsx` also reads this store before generation; if unauthenticated, it persists the fully collected config via `pendingGeneration.ts` so auth redirects (including a full Google OAuth page load) do not lose trip state.

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
Booking hub with `zustand/persist` (localStorage key: `wanderplanner-bookings`).

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
├── main.py                   — FastAPI app, CORS (allow_credentials=False), rate-limit
│                               middleware, structured logging setup, router registration
├── db.py                     — Async SQLAlchemy engine/session setup for Postgres
├── db_models/                — `users`, `refresh_tokens`, `events`, `password_reset_tokens`
├── migrations/               — Alembic migrations (`0001_auth_analytics`, `0002_password_reset`)
├── core/
│   ├── config.py             — Settings (env vars) — includes hybrid_search_enabled,
│   │                           hyde_enabled, reranking_enabled, osm_*, itinerary_cache_*,
│   │                           database/auth/email settings, pexels_api_key, allowed_origins
│   │                           wildcard validator (⭐ NEW v10.0)
│   ├── security.py           — Argon2id password hashing + JWT / opaque refresh-token helpers
│   ├── auth_dependency.py    — `get_current_user`, `get_current_admin_user`, cookie names
│   ├── analytics.py          — Generic event logging helper
│   ├── email.py              — Resend HTTP API integration for password-reset mail
│   ├── rate_limit.py         — ⭐ NEW (v10.0): slowapi Limiter (IP-keyed), 10/min LLM
│   │                           endpoints, 30/min default
│   ├── errors.py             — ⭐ NEW (v10.0): sanitize_error() — logs full exception
│   │                           server-side, returns generic message + reference id
│   ├── prompt_guard.py       — ⭐ NEW (v10.0): neutralize()/wrap_untrusted() — redacts
│   │                           injection phrases, fences untrusted text as DATA not
│   │                           instructions before LLM prompt interpolation
│   ├── logging_config.py     — ⭐ NEW (v10.0): configure_logging() — structured JSON
│   │                           logs + RedactionFilter (emails/API keys/phone numbers)
│   ├── qdrant.py             — Qdrant client singleton + collection bootstrap (4 collections)
│   ├── embeddings.py         — sentence-transformers model singleton + embed() +
│   │                           get_reranker()/rerank_scores() (cross-encoder, ⭐ NEW v9.0)
│   └── scheduler.py          — APScheduler jobs: reddit refresh (6h), OSM POI refresh (weekly, ⭐ NEW v9.0)
├── chains/
│   ├── itinerary_chain.py    — Gemini/Groq/Ollama itinerary gen (5× retry + 3-tier RAG fallback)
│   ├── chat_refine_chain.py  — Anya post-gen chat (patch_config / regenerate actions)
│   ├── wizard_chat_chain.py  — Anya LLM wizard (collects TripConfig conversationally)
│   ├── extract_trip_chain.py — URL/text → structured trip fields (Start Anywhere)
│   └── ...
├── routers/
│   ├── auth.py               — `/api/auth/*` signup/login/google/refresh/logout/me/password reset
│   ├── admin.py              — `/api/admin/metrics/*` analytics summaries (admin-only)
│   ├── analytics.py          — `/api/analytics/client-event` beacon sink
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
│   ├── search.py             — semantic_search() (hybrid BM25+semantic) + retrieve_context()
│   │                           (HyDE + 3-query RRF + optional cross-encoder rerank) +
│   │                           summarise_context() · _rrf_merge() · _time_decay_score() ·
│   │                           _bm25_search_collection_sync() · _rerank() (all ⭐ NEW/updated v9.0)
│   ├── hyde.py                — ⭐ NEW (v9.0): template-based hypothetical passage generator
│   ├── itinerary_cache.py     — ⭐ NEW (v9.0): Tier-1 fallback — cache key, get/store cached itineraries
│   ├── rag_fallback.py        — ⭐ NEW (v9.0): Tier-2 fallback — OSM-grounded itinerary skeleton
│   ├── geocode.py             — Nominatim proxy (1 req/s rate limit, LRU cache, is_country)
│   └── pexels.py              — Async Pexels client + in-memory query cache for itinerary day photos
├── scrapers/
│   ├── reddit.py             — Reddit JSON scraper → Qdrant ingestion
│   ├── wikivoyage.py         — Wikivoyage HTML scraper → Qdrant ingestion
│   └── osm.py                 — ⭐ NEW (v9.0): Overpass API POI scraper → Qdrant 'osm_pois' ingestion
├── eval/                      — ⭐ NEW (v9.0)
│   ├── golden_dataset.json    — curated corpus + labeled queries for retrieval eval
│   └── run_rag_eval.py        — Precision@k/Recall@k/MRR/nDCG@k against semantic_search()
├── load_test_rag.py           — ⭐ NEW (v9.0): concurrent-request throughput/latency load test
└── models/
    ├── common.py              — GeocodeResponse (+ is_country: bool)
    └── itinerary.py           — ItineraryDay / ItineraryItem schemas (+ optional day image attribution fields)
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

### Itinerary Day Photo Enrichment (Pexels)

`apps/api/services/pexels.py` provides an async, fail-safe client for optional itinerary day hero images. The enrichment sits on the success path of `generate_itinerary()` *after* the itinerary days have been built/scored, but *before* the response is returned.

**Architecture details:**
- `get_day_photo(query)` issues a single landscape-photo search and returns `{ url, photographer, photographer_url }` or `None`.
- Missing `PEXELS_API_KEY`, empty results, network failures, or parsing errors all degrade silently to `None` so photo lookup can never fail the itinerary request.
- A module-level in-memory cache is keyed by the exact query string and capped at 500 entries to avoid repeated searches for common destination/theme combinations.
- `get_day_photos(queries)` runs searches concurrently via `asyncio.gather()`.
- `chains/itinerary_chain.py` builds queries as `"{destination city or country} {day theme}"`, applies a 6-second overall timeout budget, logs failures, and swallows them.
- `models/itinerary.py` and `apps/web/types/index.ts` now expose `image_url`, `image_photographer`, and `image_photographer_url` on each `ItineraryDay`.

---

## 6A. Authentication & Session Management

### Account creation & providers

Authentication is brand new in this release. WanderPlanner now supports:

- **Email + password** signup/login (`POST /api/auth/signup`, `POST /api/auth/login`)
- **Google SSO** via a manual OAuth 2.0 Authorization Code flow (`GET /api/auth/google/start`, `GET /api/auth/google/callback`)
- **Password reset** via Resend-delivered reset links

The backend stores users in Postgres (`users` table) with:
- `email`
- `password_hash` (Argon2id; never plaintext)
- `display_name`
- `auth_provider` (`password` or `google`)
- `google_sub`
- `is_admin`
- `consent_accepted` + `consent_accepted_at`

**Hosting decision:** production uses **Supabase-managed Postgres** rather than self-hosted SQLite or file-backed storage. SQLite was rejected because concurrent multi-instance Railway deployments would introduce file-locking and durability issues; Neon and Railway Postgres were considered, but Supabase won on the team's free-tier / managed-ops tradeoff.

**Google SSO design note:** the app does **not** use server-side session middleware for OAuth state. Instead, it signs a stateless `state` payload with `itsdangerous.URLSafeTimedSerializer`, exchanges the code with Google's token endpoint, then fetches profile data from `openidconnect.googleapis.com/v1/userinfo` via `httpx`.

### Cookie-based session model

Sessions are stored in **httpOnly cookies**, not localStorage:

| Cookie | Purpose | Default TTL | Storage model |
|---|---|---|---|
| `wp_access_token` | Short-lived JWT for authenticated API access | ~15 minutes | Signed token |
| `wp_refresh_token` | Long-lived opaque token for session renewal | ~30 days | Raw token only in cookie; SHA-256 hash stored in `refresh_tokens` |

Refresh tokens rotate on every `POST /api/auth/refresh` call. The old token is revoked, a brand new token pair is issued, and only the hashed opaque refresh token is persisted. `refresh_tokens.user_id` uses `ON DELETE CASCADE`, so account deletion automatically revokes all remembered sessions.

`COOKIE_SAMESITE` should stay **`lax` for local dev** but switch to **`none` with `COOKIE_SECURE=true` in production**, because the frontend and backend are typically deployed on different origins (Vercel + Railway).

### Itinerary generation auth gate + frontend resume

`POST /api/generate-itinerary` now depends on `get_current_user`. Unauthenticated requests return **401**, and the frontend maps this to the `AUTH_REQUIRED` error code.

`LLMWizard.tsx` proactively checks `authStore` before calling `streamItinerary()`:

1. If the user is signed out, it serializes the fully collected trip config into `sessionStorage` via `pendingGeneration.ts`.
2. It redirects to `/signup?returnTo=/`.
3. After signup/login/Google OAuth completes, `AuthHydrator` restores the session.
4. An effect in `LLMWizard.tsx` detects both **authenticated user + pending config** and auto-resumes generation without re-asking the wizard questions.

This design preserves intent even across a full-page Google OAuth round-trip that would otherwise destroy in-memory SPA state.

### Password reset flow

`POST /api/auth/password/forgot` always returns **200** even when an email does not exist, preventing account enumeration. Reset links are backed by the `password_reset_tokens` table:

- hashed token only (never raw token at rest)
- single-use
- ~30 minute TTL (`PASSWORD_RESET_TOKEN_TTL_MINUTES`)
- `user_id` with `ON DELETE CASCADE`

`POST /api/auth/password/reset` verifies the token, updates the Argon2id password hash, and invalidates **all** of that user's existing refresh tokens as a defensive measure.

### Consent capture, legal pages, and erasure

Signup requires a single minimized consent checkbox linking to `/terms` and `/privacy`, mirroring common Indian travel-product patterns. The full legal text lives on dedicated pages and is drafted around DPDP Act-aligned concepts such as purpose limitation, named processors, grievance redressal, and deletion rights.

Self-service erasure is live via `DELETE /api/auth/me` and the `/account` page's danger zone. Deleting a user:

- cascades `refresh_tokens` via `ON DELETE CASCADE`
- cascades `password_reset_tokens` via `ON DELETE CASCADE`
- nulls `events.user_id` via `ON DELETE SET NULL` so aggregate analytics survive in anonymized form

**Admin bulk purge:** planned/in progress only. The documented admin bulk-delete endpoints/UI are **not** fully shipped in the current verified codepath.

### Auth status in the nav (⭐ NEW)

`UserMenu.tsx` is the single source of truth for session-aware UI across the app shell — see Section 9 for details. Before this, the main app had zero visible sign-in state: no "Log in / Sign up" CTA, no indicator when already authenticated, and no discoverable logout affordance outside of `/account`.

### Local dev note: SQLite foreign-key enforcement

Production runs on Postgres, where `ON DELETE CASCADE` / `ON DELETE SET NULL` are enforced by the DB engine unconditionally. When testing locally against SQLite (`apps/api/dev.db`), foreign keys are **off by default** — cascades silently no-op unless `PRAGMA foreign_keys=ON` is set per connection. `apps/api/db.py` now does this automatically via a SQLite-only `event.listens_for(engine.sync_engine, "connect")` hook (guarded by `engine.url.get_backend_name() == "sqlite"`), so local cascade-delete behavior now matches production. No effect on Postgres.

---

## 7. API Reference

### `POST /api/auth/signup`
Creates a new account with email/password + consent capture. Public endpoint.

**Request:**
```json
{
  "email": "traveller@example.com",
  "password": "strong password",
  "display_name": "Anya Fan",
  "consent_accepted": true
}
```

**Response:** `UserResponse` + sets `wp_access_token` and `wp_refresh_token` cookies.

### `POST /api/auth/login`
Email/password sign-in. Public endpoint.

**Request:** `{ "email": "traveller@example.com", "password": "..." }`
**Response:** `UserResponse` + fresh auth cookies

### `GET /api/auth/google/start`
Starts the Google OAuth flow. Public endpoint. Redirects the browser to Google's consent screen with a signed stateless `state` payload.

### `GET /api/auth/google/callback`
Completes the Google OAuth flow. Public endpoint. Exchanges the auth code, upserts/finds the user, sets auth cookies, and redirects back to the frontend.

### `POST /api/auth/refresh`
Rotates the opaque refresh token and issues a fresh access token. Requires the `wp_refresh_token` cookie.

### `POST /api/auth/logout`
Clears auth cookies and revokes the current refresh token session.

### `GET /api/auth/me`
Returns the current signed-in user. Requires auth.

### `DELETE /api/auth/me`
Self-service account deletion. Requires auth. Permanently deletes the user row, cascades refresh/password-reset tokens, and anonymizes analytics events by nulling `events.user_id`.

### `POST /api/auth/password/forgot`
Starts the password-reset flow. Public endpoint. Always returns 200 regardless of whether the email exists.

**Request:** `{ "email": "traveller@example.com" }`

### `POST /api/auth/password/reset`
Completes the password reset with a single-use token. Public endpoint.

**Request:** `{ "token": "raw reset token", "new_password": "..." }`

### `POST /api/wizard-chat` ⭐ NEW (v5.0)
LLM-powered Anya wizard. Collects TripConfig fields through natural conversation.

**Request:**
```json
{
  "messages": [{ "role": "user|assistant", "content": "...", "config_patch": {} }],
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
  "summary": "7 days in Bali - Rs 80,000 - 2 adults - Moderate pace"
}
```

`ready_to_generate` is `true` only when all 6 required fields are present *and* the Stage-2 checkpoint has completed (server-side validated). `summary` is populated when ready and is the frontend's source of truth for showing the generate CTA.

Wizard replies also go through a reliability pass in `wizard_chat_chain.py`: Gemini now runs with `max_output_tokens=2048`, every response is checked with `_looks_like_valid_json()` before being accepted, `_strip_trailing_json_artifacts()` cleans fallback text before display, and `_strip_leaked_schema_tail()` trims cases where the `reply` string itself accidentally contains an escaped echo of the remaining response schema.

### `POST /api/generate-itinerary`
Streaming SSE. Generates day-by-day itinerary from `TripConfig`. **Requires auth**; unauthenticated callers receive HTTP 401, which the frontend maps to `AUTH_REQUIRED` and uses to trigger the sign-in redirect + auto-resume flow.

**Request:** `{ trip_config: TripConfig }`  
**Response:** Server-Sent Events → final `ItineraryResponse`

Each `ItineraryDay` may now also include optional `image_url`, `image_photographer`, and `image_photographer_url` fields populated by the best-effort Pexels enrichment pass.

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
Serializes itinerary + config to an in-memory store, returns a shareable slug. Rate-limited 10/min per IP (⭐ NEW v10.0).

**Request:**
```json
{
  "itinerary": { "days": [...], "alignment_score": 87 },
  "trip_config": { ... },
  "labels": { "destination": "Bali, Indonesia", "duration": "7 days" },
  "destination_label": "Bali, Indonesia"
}
```
**Response:** `{ "slug": "bS6AneQqDEye_NRSjOFCpg", "url": "/t/bS6AneQqDEye_NRSjOFCpg" }`

Slug is `secrets.token_urlsafe(16)` (128-bit, ⭐ UPD v10.0 — was `uuid4().hex[:8]`, 32-bit).

### `GET /api/share/{slug}` ⭐ NEW
Returns stored trip data for a slug. Returns 404 if not found. Rate-limited 10/min per IP.

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

### `POST /api/analytics/client-event`
Lightweight client-side analytics beacon sink. Accepts only allowlisted event types such as `session_start`, `youtube_thumbnail_call`, and `youtube_thumbnail_failed`. Optional auth; anonymous session starts are allowed.

**Request:** `{ "event_type": "session_start", "metadata": { ... } }`

### `GET /api/admin/metrics/summary`
Admin-only summary metrics. Requires `is_admin=true`; authenticated non-admins receive **403** (not 401) so the frontend can distinguish "not allowed" from "not signed in".

**Current buckets:**
- total users
- signups (today / 7d / 30d)
- sessions (`session_start`)
- login success/failure
- itinerary generated/failed
- `cost_usage` summary (Gemini/Pexels counters; Gemini token-cost instrumentation is partially in progress)

### `GET /api/admin/metrics/timeseries`
Admin-only daily event rollups for `7d` or `30d`.

**Query params:** `range=7d|30d`

**Response:** `{ "range": "30d", "series": { "2026-07-07": { "signup": 4, "session_start": 17, ... } } }`

### `POST /api/admin/requests` ⭐ NEW
Any authenticated non-admin user requests admin access. Body: `{ "message": "optional reason" }`. Idempotent while pending; **400** if already admin. Emails every existing admin.

### `GET /api/admin/requests/me` ⭐ NEW
Caller's own most recent admin-access request (or `null`), for account-page status display.

### `GET /api/admin/requests` ⭐ NEW
Admin-only. Lists admin-access requests. **Query params:** `status=pending|approved|rejected|all` (default `pending`).

### `POST /api/admin/requests/{request_id}/approve` ⭐ NEW
Admin-only. Sets the target user's `is_admin=True`, marks the request `approved`, emails the requester. **400** if the request isn't currently `pending`.

### `POST /api/admin/requests/{request_id}/reject` ⭐ NEW
Admin-only. Marks the request `rejected` (target user's `is_admin` stays unchanged), emails the requester. **400** if the request isn't currently `pending`.

---

## 7A. Admin Analytics Dashboard

The analytics backend and the `/admin` frontend dashboard page are both live and verified end-to-end (see Section 14 changelog for verification notes).

### Data model

The `events` table is intentionally generic:

| Column | Purpose |
|---|---|
| `event_type` | String identifier (`signup`, `login_success`, `session_start`, `itinerary_generated`, etc.) |
| `event_metadata` | JSONB blob for event-specific detail without forcing schema migrations |
| `user_id` | Nullable FK to `users.id` with `ON DELETE SET NULL` |
| `created_at` | Indexed event timestamp |

This lets WanderPlanner add new analytics classes — especially model-usage and cost events — without churning migrations every time a new metric is introduced.

### Access control

Admin access is enforced with `get_current_admin_user`:

- unauthenticated caller → **401**
- authenticated non-admin caller → **403**
- authenticated admin caller → success

That 403-vs-401 split is deliberate so the frontend can render the right UX.

**Nobody becomes an admin automatically.** `SignupRequest` (`models/auth.py`) has no `is_admin` field at all, so it is structurally impossible for the signup payload to grant admin access; `User.is_admin` defaults to `False` at the DB layer (`db_models/user.py`). The only two ways `is_admin` is ever flipped to `True`:

1. **Out-of-band DB seed** — used once, to create the very first admin, since no admin exists yet to approve one.
2. **The admin-request approval workflow** (⭐ NEW — see below) — an existing admin explicitly reviews and approves a request.

### Admin access requests (⭐ NEW)

New `admin_requests` table (migration `0003_admin_requests`):

| Column | Purpose |
|---|---|
| `user_id` | FK → `users.id`, `ON DELETE CASCADE` |
| `status` | `"pending"` \| `"approved"` \| `"rejected"` |
| `message` | Optional free-text reason from the requester |
| `reviewed_by` | FK → `users.id`, `ON DELETE SET NULL` — which admin actioned it |
| `reviewed_at` | Timestamp of the approve/reject decision |

**Flow:**
1. Any authenticated non-admin user calls `POST /api/admin/requests` (from `/account` → "Admin access" section). Idempotent — calling it again while a request is still pending returns the existing pending request rather than creating a duplicate. Already-admin users get a **400**.
2. Every existing admin (`User.is_admin=true` with a non-null email) is emailed via `core/email.send_admin_request_notification` — best-effort, never blocks the request itself; in local dev without `RESEND_API_KEY` the notification is logged instead (same pattern as the password-reset dev-log fallback).
3. Any admin sees all pending requests in the `/admin` console's "Admin access requests" panel (`GET /api/admin/requests?status=pending`), with the requester's name/email and optional message.
4. The admin clicks **Approve** (`POST /api/admin/requests/{id}/approve`) or **Reject** (`POST /api/admin/requests/{id}/reject`). Approval sets the target user's `is_admin=True` and emails them a decision notification (`core/email.send_admin_request_decision_email`); rejection leaves `is_admin=False` and still notifies them. Both actions are idempotent-guarded — a request that's already `approved`/`rejected` returns **400** on a second review attempt.
5. `GET /api/admin/requests/me` lets the requester's own `/account` page show "pending review" / "declined, request again" state without granting anything.

All state-changing admin-request actions are logged as analytics events (`admin_request_created`, `admin_request_approved`, `admin_request_rejected`) for audit trail.

### Metrics currently exposed

- `GET /api/admin/metrics/summary`
- `GET /api/admin/metrics/timeseries`
- `POST /api/analytics/client-event` for browser-originated events the backend would not otherwise see

Tracked today:
- signups
- session starts
- login success/failure
- itinerary generation success/failure
- Pexels call volume

### Cost tracking status

The admin summary endpoint returns live-aggregated fields for:

- `gemini_requests_30d`
- `gemini_tokens_30d`
- `gemini_estimated_cost_inr_30d` (⭐ displayed in INR, not USD — see Section 6A/14 note on `usd_to_inr_rate`)
- `pexels_calls_30d`

Gemini token/cost event instrumentation (`core/llm_usage.py`, `core/llm_client.py`) is fully wired end-to-end and verified against real Gemini API calls — each request logs a `gemini_usage` event with real token counts and an internally-USD-computed cost, which the admin summary endpoint sums and converts to INR for display.

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
| **Anya wizard chat** (`/api/wizard-chat`) | **0.4** | **2048** | Conversational, friendlier but more deterministic extraction; larger budget reduces mid-JSON truncation |
| **Anya post-gen chat** (`/api/chat-refine`) | **0.5** | **1024** | Semi-deterministic refinements |
| City recommendations | 0.4 | 1024 | Structured JSON output |
| Destination comparison | — | — | 10-param scoring |
| Trip extraction (Start Anywhere) | 0.1 | 512 | Near-deterministic extraction |

---

### RAG Architecture (Retrieval-Augmented Generation)

WanderPlanner uses RAG to inject real traveller knowledge from Reddit, Wikivoyage, and (new) OpenStreetMap into Gemini's itinerary generation prompt. As of v9.0, retrieval is hybrid (BM25 + semantic), augmented with HyDE, optionally reranked with a cross-encoder for the primary generation path, and backed by a 3-tier RAG-powered fallback chain for LLM outages.

#### How It Works

```
1. INGESTION (startup + every 6h, OSM weekly)
   ┌──────────────────────────────────────────────────────┐
   │ scrapers/wikivoyage.py                               │
   │   → Scrape sections (See, Eat, Do, Drink, Sleep...)  │
   │   → _sentence_boundary_chunks(): ~500 chars/chunk    │
   │      (splits at sentence boundaries, not char count) │
   │   → Unique ID: md5(url + section + text[:50])        │
   │   → embed via all-MiniLM-L6-v2 (384 dims)           │
   │   → upsert into Qdrant 'wiki' collection             │
   └──────────────────────────────────────────────────────┘
   ┌──────────────────────────────────────────────────────┐
   │ scrapers/reddit.py                                   │
   │   → Reddit JSON API (r/travel, r/solotravel, ...)    │
   │   → _extract_destination(): regex against 200+ dests │
   │   → _chunk_reddit_post(): paragraph-level chunks     │
   │      each chunk = title prefix + paragraph (≥80 chars)│
   │   → stores published_date from created_utc           │
   │   → upsert into Qdrant 'reddit' collection            │
   └──────────────────────────────────────────────────────┘
   ┌──────────────────────────────────────────────────────┐
   │ scrapers/osm.py ⭐ NEW (v9.0)                          │
   │   → Overpass API (free, no key) — ~14 POI tag categories │
   │   → Geocodes destination via services/geocode.py      │
   │   → Dedupes by name, builds short embeddable description │
   │   → upsert into Qdrant 'osm_pois' collection           │
   │   → Scheduled weekly (core/scheduler.py)               │
   └──────────────────────────────────────────────────────┘

2. RETRIEVAL (at itinerary generation time)
   services/search.py → retrieve_context(trip_config, enable_reranking=True)
   │
   ├─ Build 3 query variants:
   │    Q1: "{dest} travel {personas} highlights activities food"
   │    Q2: "things to do in {dest} {purpose} {pace} hidden gems"  ← HyDE-augmented
   │    Q3: "{dest} best restaurants sightseeing transport safety"
   │
   ├─ HyDE (services/hyde.py) ⭐ NEW (v9.0): Q2's embedding target is replaced with a
   │    synthesized hypothetical travel-guide passage (template-based — persona/pace/
   │    purpose hooks, no LLM round-trip) before embedding
   │
   ├─ asyncio.gather() — run all 3 in parallel (limit=15 each), each offloaded via
   │    asyncio.to_thread() so embed()/Qdrant calls run on real worker threads
   │    (fixed a concurrency bug this cycle where they previously serialized on the
   │    event loop despite gather())
   │
   ├─ Hybrid search per query ⭐ NEW (v9.0): BM25 (Qdrant scroll, destination-scoped,
   │    rank_bm25.BM25Okapi) run alongside the semantic cosine search, fused via RRF
   │
   ├─ _rrf_merge(): Reciprocal Rank Fusion (k=60)
   │    Score = Σ 1/(60 + rank_i) across all query lists
   │
   ├─ Cross-encoder reranking ⭐ NEW (v9.0, ms-marco-MiniLM-L-6-v2): reranks top-40
   │    candidates by scoring (query, doc) pairs jointly. Fails safe — falls back to
   │    RRF order on any exception. Only enabled for this call site
   │    (settings.reranking_enabled=False by default; enable_reranking=True passed
   │    explicitly only from the Gemini and Groq/Ollama itinerary-generation paths,
   │    since a cross-encoder pass adds real latency — see load test numbers below)
   │
   └─ Return top-20 merged/reranked chunks

3. COMPRESSION (summarise_context)
   │
   ├─ _time_decay_score(): half-life 18 months, floor 40%
   │    1 month ago → 0.978×, 1 year → 0.778×, 3 years → 0.550×
   │
   ├─ Score filter: drop decayed score < 0.35
   │
   ├─ Jaccard dedup: >0.60 word overlap → keep highest scored
   │
   ├─ Sort by decayed score DESC
   │
   └─ Truncate at 2400 chars (~600 tokens, 12× reduction vs old 7500)

3B. CORPUS FEW-SHOT RETRIEVAL ⭐ NEW (v10.15, docs/rag-strategy.md §9)
   services/search.py → retrieve_itinerary_examples(trip_config)
   │    (called best-effort via itinerary_chain.py::_itinerary_examples_block;
   │     gated by settings.itinerary_corpus_retrieval_enabled, default True)
   │
   ├─ Config-style query mirroring the ingest-side _config_text():
   │    "{duration} day {pace} {purpose} {group_type} trip {city} {country}"
   │
   ├─ Searches BOTH named vectors of `itinerary_corpus` (config + content)
   │    with a destination payload filter; unfiltered fallback with
   │    case-insensitive client-side city match (extraction LLM writes
   │    free-form destination strings — never inject another city's trip)
   │
   ├─ Weighted merge 60% config / 40% content (per §9 embedding strategy),
   │    × (0.5 + 0.5 × quality_score) source-authority weighting,
   │    relevance floor 0.45
   │
   └─ Top ≤3 formatted as "[Source: … — 5 days, moderate, cultural, couple]
        Day 1: … Places: …" and wrap_untrusted()'d for prompt injection

4. AUGMENTATION (itinerary_chain.py)
   context_text = summarise_context(context_docs, max_chars=2400)
   prompt = SYSTEM_PROMPT.format(
       context=context_text,          # ← real traveller data
       itinerary_examples=...,        # ← ≤3 real traveller itineraries ⭐ NEW (v10.15)
       trip_config=trip_config_json
   )
   → Gemini generates itinerary grounded in real traveller data; the
     REAL TRAVELLER ITINERARIES FOR REFERENCE section grounds pacing,
     day sequencing, and realistic same-day place groupings (the prompt
     instructs "inspiration, not verbatim"; degraded sentinel is
     "No reference itineraries available." when the corpus has no match)

5. FALLBACK ⭐ NEW (v9.0) — if all LLM attempts fail:
   Tier 1: itinerary_cache lookup (services/itinerary_cache.py, cosine ≥ 0.88) → instant hit
   Tier 2: rag_skeleton_itinerary() (services/rag_fallback.py) → real OSM POIs slotted
           into a day structure by pace; requires ≥3 ingested POIs for the destination
   Tier 3: _mock_itinerary(tip_texts=...) → static mock enhanced with real retrieved
           wiki/reddit snippets spliced in as "Local tip: ..." (always succeeds)
   On success, store_itinerary() caches the result (best-effort; strips any "_"-prefixed
   fallback markers so degraded output is never cached and re-served as genuine).
```

**Latency tradeoff (measured via `apps/api/load_test_rag.py`, concurrency=50):**

| Configuration | Throughput |
|---|---|
| Original (pre-concurrency-fix) | ~10 req/s |
| + `asyncio.to_thread` fix + batch embedding | ~23.6 req/s |
| + hybrid BM25 + HyDE + reranking (all enabled globally) | ~7 req/s |
| + reranking scoped to itinerary generation only (current) | ~13.5 req/s |

Reranking is the dominant cost (a cross-encoder forward pass per candidate); scoping it to only the primary generation path — where LLM latency already dominates the request — keeps `/api/search` and other lightweight RAG callers fast.

#### Example RAG Context Injection

**User trip:** Bali, 7 days, Beach + Culture themes, moderate pace

**Queries sent to Qdrant (parallel):**
1. `"Bali travel beach culture highlights activities food"`
2. HyDE-synthesized passage for `"things to do in Bali leisure moderate trip hidden gems local tips"`
3. `"Bali best restaurants sightseeing transport safety advice"`

**Retrieved & compressed context (sample, after hybrid search + RRF + rerank + time-decay + dedup):**

> *[reddit/solotravel]* "Ubud rice terraces: go at 7am to beat tourists. Best warung meal near the palace — Warung Babi Guling Ibu Oka." *(decayed score: 0.87)*

> *[wikivoyage/Bali/See]* "Tanah Lot temple is best visited at sunset. Accessible at low tide only. One of Bali's most photographed sites." *(decayed score: 0.82)*

> *[reddit/travel]* "Hire a driver for the day (~$40 USD) for Uluwatu + Kuta. Safer than scooter and they know Kecak fire dance timing." *(decayed score: 0.79)*

These chunks are injected under `DESTINATION RESEARCH:` in the prompt.

If Qdrant is empty (cold start), the chain falls back to:
```
context = "No pre-fetched research available — use your own knowledge of the destination."
```

#### Embedding Model
- **Model:** `sentence-transformers/all-MiniLM-L6-v2`
- **Dimensions:** 384
- **Distance metric:** Cosine similarity
- **Runs locally** — no API key, no network call for embeddings

#### Reranking Model
- **Model:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (`core/embeddings.py::get_reranker()`)
- **Runs locally** — no API key; lazily loaded singleton
- **Scope:** only the final itinerary-generation retrieval call (see latency tradeoff above)

#### Golden Dataset & Retrieval Evaluation
- `apps/api/eval/golden_dataset.json` — curated corpus + labeled queries with expected-relevant chunk IDs
- `apps/api/eval/run_rag_eval.py` — computes Precision@k, Recall@k, MRR, nDCG@k against `semantic_search()` (exercises hybrid BM25, not HyDE/reranking — those live only inside `retrieve_context()`)
- Current results: Recall@10 = 1.00, MRR ≈ 0.85–0.94, nDCG@10 ≈ 0.89–0.96 (see `docs/eval-set.md` for full methodology and how to run)

---

### System Prompt 1: Anya Wizard (`/api/wizard-chat`)

**File:** `apps/api/chains/wizard_chat_chain.py`  
**Temperature:** 0.4 · **Max tokens:** 2048  
**Version:** v5 (June 2026) — JSON history replay, stricter extraction, smart fallback

**Key sections:**
- **System Purpose** — Anya is a human travel professional speaking to a customer, not a slot-filling agent. Explicitly prohibits narrating internal logic.
- **Persona & Tone** — warm Indian travel expert friend; 2-3 sentences max; TTS-optimised
- **Absolute Speaking Rules (§1a)** — hard prohibition on field names, system terms (`config_patch`, `destination_mode`, `missing field`), and internal reasoning in `reply`. Three verbatim WRONG/RIGHT examples from real failure cases.
- **Indian Cultural Context** — currency parsing (25k→25000, 1L→100000), travel seasons (Oct-Nov Diwali, Apr-May school holidays), joint family norms, veg/Jain food sensitivity
- **Audio/STT Handling** — Hinglish glossary (araam se→relaxed, family ke saath→family, bas karo→generate), filler word stripping, number speech (seven days→7)
- **6 Required Fields** — each with JSON key, valid values, and explicit phrase mappings
- **Optional Fields** — auto-inferred themes (honeymoon→wellness, adventure purpose→adventure)
- **Slot Filling** — never re-ask collected fields; defaults for "surprise me" (leisure, 6 days, 1L, moderate)
- **3-Stage Flow** — Stage 1: collect 6 fields → Stage 2: "anything else?" checkpoint → Stage 3: generate signal
- **config_patch Rules** — "include every extracted field even if you think it is already known" and never return an empty patch when the user just supplied usable trip details
- **JSON-Wrapped History** — assistant messages are replayed to Gemini as JSON containing the actual `reply` and `config_patch` from that turn, improving extraction consistency
- **Retry Logic** — 3 attempts with exponential backoff on 503/429/UNAVAILABLE *and* on successfully returned-but-invalid JSON detected by `_looks_like_valid_json()`
- **Fallback Text Cleanup** — `_strip_trailing_json_artifacts()` removes stray trailing `",`, `}` or `]` fragments before salvage text is shown to the user
- **Schema-Echo Cleanup** — `_strip_leaked_schema_tail()` trims rare cases where the `reply` string itself contains an escaped literal echo of `chips`, `config_patch`, `ready_to_generate`, or `summary`
- **Smart Mock Fallback** — reads `partial_config` and asks the next missing required-field question
- **Filled-State Consistency** — frontend `allFilled` now uses the same `_isFieldFilled` logic as the progress pills
- **Output Schema** — JSON only; `reply` is "what Anya says on a phone call — no field names, no system terms, no reasoning"

The backend `_has_all_required()` server-validates `ready_to_generate`. Stage 2 checkpoint is tracked via `_checkpoint_asked` flag in `partialConfig` and surfaced to the LLM via `CURRENT_STATE`. Assistant history replay now uses raw-JSON leak guards and double-wrapped JSON detection before the final `_strip_leaked_reasoning()` safety net. The parser now treats incomplete-but-successful Gemini responses as retryable failures rather than immediately surfacing salvage text.

---

### System Prompt 2: Anya Post-Gen Chat (`/api/chat-refine`)

**File:** `apps/api/chains/chat_refine_chain.py`  
**Temperature:** 0.5 · **Max tokens:** 1024  
**History:** Last 10 messages

```
You are Anya, WanderPlanner's friendly AI travel assistant.

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
  "I'm Anya, WanderPlanner's travel assistant — I can only help with travel questions! 🌍"
```

---

### System Prompt 3: Itinerary Generation (`/api/generate-itinerary`)

**File:** `apps/api/chains/itinerary_chain.py`  
**Temperature:** 0.4 · **Max tokens:** 16384

```
You are WanderPlanner, an expert AI travel advisor.
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
- Theme chip groups (Culture/Food/Adventure/etc.) render as toggleable multi-select chips with a dedicated **Continue** action, driven by the backend's explicit `multi_select` flag (⭐ v10.2 — previously a fragile frontend keyword heuristic that silently broke when Gemini phrased chip labels differently); single-value chip groups still submit immediately
- Field progress pills showing which of the 6 required fields are filled
- Voice input (Web Speech API) + TTS output (Speech Synthesis API)
- "Generate my itinerary" button appears only once the backend emits the explicit Stage-3 ready signal (`summary !== null`)
- Mobile-first: bottom-sheet on mobile, centered modal on desktop
- Calls `POST /api/wizard-chat` on each message; merges `config_patch` into local state
- Keeps the free-text input available during the Stage-2 optional follow-up round instead of hiding it as soon as the 6 required fields are filled
- Replays assistant turns to Gemini as JSON-wrapped history with the real `config_patch` from each turn
- **Edit mode (⭐ v10.2):** reopening the wizard via "Edit Trip" on an already-generated itinerary detects the existing complete config + itinerary and seeds `partialConfig` from it (with `_checkpoint_asked: true`) instead of starting a fresh conversation — greets with a one-line trip summary and "Change destination/dates/budget/themes" or "Regenerate as-is" chips
- On generate: merges partial config into `tripConfigStore` → calls `streamItinerary`

### `ConversationalWizard.tsx` (legacy, kept for reference)
~2400 lines. Original rule-based wizard (11 hardcoded field steps). No longer used by `page.tsx`.

### `ChatPanel.tsx`
Persistent post-generation Anya chat. Triggered by `FloatingAnyaButton` (floating orb).

Features:
- Design token styles (full dark mode support); header includes a `ThemeToggle` (⭐ v10.2) so users can flip dark/light without closing the chat
- Calls `POST /api/chat-refine` with current `tripConfig`
- `patch_config` action: silently applies changes
- `regenerate` action: shows confirmation dialog with "Yes, apply & reset" / "Just noting it"
- Typing indicator (3 bouncing dots)
- Persists message history in `chatStore` for the session

### `ItineraryDocument.tsx`
`@react-pdf/renderer` export component for the downloadable itinerary PDF.

Features:
- Scrapbook / travel-journal visual system: one rounded pastel card per day, cycling through a 7-color palette with darker matching accents
- Optional day hero photo at the top of each card, sourced from `ItineraryDay.image_url`, with required attribution text (`Photo by {photographer} on Pexels`)
- Bold-label bullet formatting for itinerary items, link-preview-style booking chips, and compact inline transit-warning boxes
- The same colorful card treatment is reused for Trip Essentials, Visa & Safety, Cost Breakdown, and Packing Checklist sections
- ASCII-safe typography replacements for symbols that render poorly in base Helvetica (`->`, `^`, `~`, no emoji) to avoid tofu glyphs in `react-pdf`

### `PolaroidCard.tsx`
Activity card with:
- Compact horizontal layout (⭐ v10.2 redesign) — small 80–96px square thumbnail + text side-by-side, replacing the earlier full-width 16:9 hero-video layout that obscured the itinerary text on long activity lists
- Real `imageSrc` prop (Wikipedia photo or YouTube thumbnail)
- Gradient fallback via `pickGradient(title)` (deterministic hash), including on `<img onError>` (⭐ v10.2) so a thumbnail URL that later 404s (deleted/restricted video) degrades gracefully instead of showing a broken-image icon
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

### `UserMenu.tsx` ⭐ NEW
Shared auth status control, rendered in `LandingHero`'s nav, `ThreeColumnLayout`'s title bar, and `TopNav`:
- **Signed out**: renders "Log in" / "Sign up" links (`/login`, `/signup`)
- **Signed in**: renders a pill button with the user's `display_name`/`email` → click opens a dropdown with "Account settings" (`/account`), **"Admin console" (`/admin`, only rendered when `user.is_admin`)**, and "Log out" (calls `authStore.logout()`, then routes home)
- Reads `authStore.status`/`user` directly, so it reflects the live session with no extra fetch; shows a skeleton pulse while `status === 'loading' | 'idle'`
- Fixes a real bug: previously there was **no** login/signup CTA, no "you're signed in" indicator, and no way to sign out from the main app shell — `/account`'s danger-zone logout button was the only way to sign out, and it was undiscoverable without already knowing the URL

### `ThreeColumnLayout.tsx`
Three-column dashboard + full-screen map mode. **Now mobile-responsive.**

Layout (desktop `lg+`):
- **Left (25%)**: `Column1Metrics` → metrics, expenses, currency, `BookingHub` (falls back to `destination_country` and shows "City +N" when a trip resolves to a country/multi-hop rather than one fixed city — ⭐ v10.2)
- **Center (flex-1)**: top-bar with destination, `ThemeToggle` (⭐ v10.2 — previously only present on the shared `/t/[slug]` page), and `ShareButton`, then `ItineraryTimeline` or `ComparisonPanel`
- **Right (25%)**: map + "⤢ Full screen" toggle, then `Column3Sidebar` (same `destination_country` fallback for travel tips/booking links — ⭐ v10.2)

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

### Authentication + Pending-Generation Resume Flow (new)

```
User completes wizard while signed out
  → LLMWizard sees authStore.status !== authenticated
  → savePendingGeneration(fullTripConfig) to sessionStorage
  → redirect to /signup?returnTo=/

User signs up / logs in / returns from Google OAuth
  → AuthHydrator calls GET /api/auth/me
  → authStore.user becomes available
  → LLMWizard effect sees (authenticated + pendingGeneration exists)
  → restore config from sessionStorage
  → clearPendingGeneration()
  → streamItinerary(config) without re-asking questions
```

### Password Reset Flow (new)

```
/forgot-password
  → POST /api/auth/password/forgot { email }
  → always returns 200 (no email enumeration)
  → Resend sends reset link if account exists

/reset-password?token=...
  → POST /api/auth/password/reset { token, new_password }
  → backend verifies hashed single-use token + TTL
  → password hash updated
  → all refresh tokens for that user revoked
```

### Itinerary Generation Auth Gate (updated)

```
User clicks "Generate my itinerary"
  → frontend checks authStore
  ├─ signed in:
  │    → POST /api/generate-itinerary
  │    → backend get_current_user passes
  │    → normal SSE itinerary stream
  └─ signed out:
       → no API call yet; save pending config + redirect to auth page

If an unauthenticated request still reaches the backend:
  → POST /api/generate-itinerary returns 401
  → lib/api.ts maps it to AUTH_REQUIRED
  → frontend falls back to the same redirect + auto-resume flow
```

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
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/wanderplanner
JWT_SECRET=replace-with-a-long-random-secret
ACCESS_TOKEN_TTL_MINUTES=15
REFRESH_TOKEN_TTL_DAYS=30
COOKIE_DOMAIN=
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
FRONTEND_BASE_URL=http://localhost:3000
RESEND_API_KEY=
EMAIL_FROM_ADDRESS=Wanderplanner <no-reply@wanderplanner.app>
PASSWORD_RESET_TOKEN_TTL_MINUTES=30
QDRANT_URL=:memory:
PEXELS_API_KEY=                            # optional — itinerary still works without day photos
ALLOWED_ORIGINS=["http://localhost:3000"]   # JSON-array format required; "*" is rejected
LOG_LEVEL=INFO                              # structured JSON logging (⭐ NEW v10.0)
NOMINATIM_USER_AGENT=wanderplanner/1.0
NOMINATIM_RATE_LIMIT=1
```

Local development can point `DATABASE_URL` at either:
- a local Postgres instance, or
- the same Supabase Postgres used by a dev/staging environment.

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

## 14. Recent Changes (v10.21, v10.20, v10.19, v10.18, v10.17, v10.16, v10.15, v10.14, v10.13, v10.12, v10.11, v10.10, v10.9, v10.8, v10.7, v10.6, v10.5, v10.4, v10.3, v10.2, v10.1, v10.0, v9.0, v7.0, v6.0 & v5.0)

### v10.21.0 Changes (July 2026) — UI/UX audit §2.1+§2.2: dark-mode polish pass + plain-language error copy + dead-code deletion

First of the remaining UI/UX-audit milestones (2026-07-13 audit, §2.1 dark-mode gaps + §2.2 developer-speak error copy), done as one polish pass. All changes are zero-LLM, CSS/copy-level — no behaviour or API changes.

| Change | Detail |
|---|---|
| **DELETED** `components/wizard/WizardForm.tsx` + `components/wizard/sections/*` (8 files) | The legacy structured wizard was mounted nowhere (`LLMWizard` is the live path) and its sections carried the pre-rebrand `#1E40AF` palette — deleting it shrank the dark-mode fix surface, as the audit suggested. The crowd-style dial it contained is not lost product surface: `crowd_preference` is set conversationally via the live wizard/refine chain; the store default (`balanced`) is unchanged. |
| **FIXED (dark mode)** `ItineraryOverview.tsx`, `ExpenseBreakupCard.tsx`, `FeasibilityCard.tsx`, `BookingLinksSection.tsx`, `PdfDownloadButton.tsx`, `ErrorState.tsx` | All six components moved off hardcoded light-only styling (`bg-white`, `border-slate-200`, pre-rebrand `#1E40AF`/`#0F172A`) onto the design-system tokens (`var(--_card)`, `var(--_border)`, `var(--_fg)`, `var(--_primary)`, …) so the `.dark` overrides apply. Semantic status colors (feasibility green/red, budget warnings, amber error) use explicit `dark:` variants matching the existing `ItineraryTimeline`/`BookingHub` idiom. BookingHub category tab buttons also gained `aria-label`s (audit §3.3, done in passing while touching the markup). |
| **FIXED (copy)** `ErrorState.tsx` LLM_ERROR hint + `ConversationalWizard.tsx` network-error message | "Check that the backend is running and retry" → "Something went wrong on our side while generating your itinerary — please try again in a moment"; "please make sure the backend is running" → "check your internet connection and try again". Users don't run backends. |
| **Verified** | `tsc --noEmit` clean · web suite 36 passed · dark-mode verified live on the dev dashboard via computed styles (card `#071522`, border `#0E3A57`, active tab `#38BDF8` under `.dark`) — note the browser-automation pane freezes CSS transitions (the audit's known artifact), so verification disabled `transition` per element before sampling. Backend untouched (no pytest run needed). |

### v10.20.0 Changes (July 2026) — Clean live run PUBLISHED (fidelity 0.975) + trust-critical audit fixes (honest tip provenance, working booking deep-links)

The Phase 1 publish gate is cleared and the two trust-critical items from the 2026-07-13 UI/UX audit — the ones that contradicted the verified-truth wedge on production surfaces — are fixed.

| Change | Detail |
|---|---|
| **Clean live rerun** (gemini-2.5-flash override, 2026-07-14) | **Fidelity 0.975 · recall 0.938 · inclusion 1.000 · stability 1.000 · precision 0.979 · honesty 4/4.** RF-010 Singapore recovered 0.00 → 1.00 (last run's zero was transient Gemini 503s, as diagnosed); RF-012 Mumbai improved 0.33 → 0.67 with no code change (live expansion variance). Remaining misses are all recall 0.67 (RF-001/RF-009/RF-012 — expansion not proposing one truth-set place each); inclusion/stability 1.00 on every case. |
| **PUBLISHED** `docs/eval-results/` | The deliberate publish out of gitignored `eval/out/`: comparison piece (`README.md` — "Can your AI travel planner prove it listened?") + both verbatim baseline reports dated 2026-07-14. The piece leads with what we lose (ChatGPT recall 1.00 vs our 0.94), states the recording protocol (including the two corrections made in ChatGPT's favour), carries the **mandatory Claude verbal-honesty disclosure** (strict 0/4 but verbally honest 4/4, no invented places — vs ChatGPT's invented "Wizarding World Goa"), and an explicit "what we are NOT claiming" section (unverifiable ≠ hallucinated; n=20; category difference vs chatbots). The Claude report copy carries an editorial note pointing at the disclosure. |
| **FIXED (trust-critical)** `routers/travel_tips.py` — fabricated provenance removed | The Gemini prompt no longer asks for tips that "read like real travelers" with `r/travel`/TripAdvisor/Lonely Planet labels, and `_fallback_tips` no longer hardcodes fake upvote counts (127/94/156/203). Provenance is now **enforced in code, not just the prompt**: LLM and template tips always get `source="General tip"`, `score=0`, `post_url=""` regardless of what the model returns. Real Reddit tips (live search, real permalinks/scores) are unchanged. `Column3Sidebar.tsx` renders no-URL tips as plain cards instead of links. Verified live in dev: 6 "General tip" cards, 0 fake-source anchors, no scores. |
| **FIXED (trust-critical)** `BookingLinksSection.tsx` — broken flight deep-links | Google Flights moved off the retired `#search;f=…` fragment to the supported natural-language `?q=Flights from X to Y on … through …` (pre-fills from city names; degrades to "Flights to Y" when origin is unset). Skyscanner/MakeMyTrip get real IATA-coded deep-links via **NEW `lib/cityCodes.ts`** — a small static city→IATA map (~75 cities, India-first + common international; deterministic, zero-LLM) with `isIndianCode()` driving MMT's `intl` flag; when either end doesn't resolve (or dates are missing) they fall back to their search pages and the sidebar copy honestly switches from "Links open pre-filled…" to "Some links open as a search page…". Verified in dev: Delhi→Tokyo produces `del/tyo/261114/261116` (Skyscanner) and `DEL-TYO-14/11/2026_TYO-DEL-16/11/2026` (MMT). |
| **UPDATED** `app/dev/page.tsx` + `app/dev/mockData.ts` | Dev fixture now seeds origin (Delhi) + real dates so the booking-links pre-fill path is exercisable locally; the rickroll YouTube id (audit §3.4) replaced with the empty id the backend mock path uses. |
| **FIXED** `eval/run_refinement_eval.py` rescore label | Repeated `--results` rescores no longer nest "(rescored from …)" suffixes in the saved mode label. |
| **Verified** | Backend suite **223 passed** (219 + 4 new `test_travel_tips.py`: fallback labelling ×2, prompt carries no community branding ×1, structural relabel-even-if-model-fabricates ×1), 6 skipped. `tsc --noEmit` clean. Browser verification of tips + booking links on the dev dashboard (external link targets verified by construction; in-session external navigation unavailable). |

### v10.19.0 Changes (July 2026) — Live recall bugs fixed + structural pin enforcement; repeat live run: fidelity 0.904

Diagnosis-first session: before touching code, the three v10.18.2 zero-pin cases were reproduced live (~$0.02, raw Gemini responses captured). **The root cause was named-interest detection, not diacritics**: Gemini returned `named_interest: null` on all three — routing "zen gardens" and "Portuguese colonial heritage" into a `themes` config patch (RF-004/RF-014), and answering the Bengaluru question conversationally while naming places itself (RF-016, violating the no-self-naming rule). The repro also caught a fourth, unsuspected bug: candidate "Ginkaku-ji" was pinned as "Kinkaku-ji" because verification took the first fuzzy hit (ratio 0.89) in scroll order instead of the later exact match.

| Change | Detail |
|---|---|
| **UPDATED** `chains/chat_refine_chain.py` detection prompt | NAMED INTEREST DETECTION broadened beyond fandoms: any concrete interest (cultural themes, heritage, food, nature, architecture) counts, question phrasings included ("what does Bengaluru have for palace lovers?"), with explicit examples from the failing cases. Reply rule strengthened: never name places yourself, even when answering a question. |
| **NEW** deterministic themes-patch backstop in `_apply_interest_pinning` | When the refine LLM leaves `named_interest` null but the patch adds NEW themes (vs the trip's existing ones, case-insensitive), the interest label is derived from those themes (join of first 2). Zero extra LLM calls; verification still gates every pin. Covers the exact live failure mode even if the model regresses on the prompt. |
| **FIXED** `services/poi_pinning.py` — `_normalize` diacritic folding + `_best_osm_match` | `_normalize` now NFKD-folds diacritics to base letters (Ryōan-ji → ryoan ji, Sé → se) so accented candidates hit exact/containment matches instead of surviving only on fuzzy ratio. New `_best_osm_match`: strongest match wins — exact, then containment, then fuzzy — replacing first-fuzzy-hit-in-scroll-order (the Ginkaku-ji/Kinkaku-ji mis-pin). |
| **NEW** `chains/itinerary_chain.py::_enforce_pins` — structural exactly-once enforcement | The PINNED prompt block is now a request, not the guarantee: after generation + post-processing filters, `_enforce_pins()` matches item titles against pins with the production matcher, tags the first match, untags duplicates, and injects any dropped pin (evening slot, lightest day, verified coords — same shape as the mock path). Pure CPU, zero LLM, all generation paths incl. fallbacks. Fixes RF-007 Barcelona (1-of-3 pins honoured live in v10.18.2). |
| **UPDATED** `chains/interest_expansion_chain.py` prompt | Anti-distractor rule (place must be known FOR the interest, not merely popular at the destination — RF-001 Borough Market over-reach) + heritage-quarter allowance (a named district counts when the district itself is the attraction — RF-014 Fontainhas was being suppressed by the blanket "no neighbourhoods" rule). |
| **Repeat live run (gemini-2.5-flash override)** | **Fidelity 0.904 · recall 0.854 · inclusion 0.938 · stability 0.938 · precision 0.917 · honesty 4/4.** All three v10.18.2 zero-cases and Barcelona now score 1.00. Inclusion/stability are 1.00 on every case that produced pins (the 0.938 aggregates are dragged only by RF-010). Remaining blemishes: RF-010 Singapore 0.00 — persistent Gemini 503s killed the expansion call during the run (transient infra, visible in the log, not a pipeline bug; rerun before publishing); RF-012 Mumbai recall 0.33 (Film City pinned; Mannat/Prithvi Theatre not proposed live); RF-001/RF-009 recall 0.67. Both baseline comparison reports regenerated in `eval/out/` (vs ChatGPT 1.000 recall / 0.743 unverifiable / 0% honesty; vs Claude Sonnet 0.979 / 0.786 / 0% strict-honesty with the verbal-honesty nuance documented in-file). |
| **Verified** | Backend suite **219 passed** (207 + 12 new: diacritic normalize/match ×3, exact-beats-fuzzy ×1, themes-backstop ×4, `_enforce_pins` ×4), 6 skipped. Offline eval gate: 1.000 / 100% honesty. Live spot-check of the three fixed cases before the full run: all pinned verified places. |

### v10.18.2 Changes (July 2026) — First live kill-criterion run + ChatGPT & Claude Sonnet baselines

The GTM Phase 1 gate (§5) now has real numbers on all three systems, scored with the same matcher against the same fixture truth-set.

| Change | Detail |
|---|---|
| **Live WanderPlanner run** (gemini-2.5-flash via env override; flash-lite was congested) | Fidelity **0.771** · pin recall **0.750** · inclusion **0.771** · stability **0.812** · precision **0.792** · honesty **4/4 (100%)**. 13/16 positive cases ≥0.87; three scored **zero pins** (RF-004 Kyoto zen, RF-014 Goa Portuguese heritage, RF-016 Bengaluru palaces/gardens — live detection/expansion produced nothing; suspects: diacritics in place names (Ryōan-ji/Sé Cathedral) and interest phrasings not detected as `named_interest`). RF-007 Barcelona: all 3 pins correct but only 1 appeared exactly-once with the `pinned` tag in the generated itinerary (generation-compliance gap). RF-001 London pinned distractor Borough Market (expansion over-reach; precision hit). These are the next-session fix list — publish only after they're addressed and the live run is repeated. |
| **NEW** `eval/baselines/chatgpt_refinement.json` | Founder-recorded ChatGPT free-tier answers (template protocol; two mechanical splits made in ChatGPT's favour, disclosed in-file). Scores: verified-POI recall **1.000**, unverifiable-suggestion rate **0.747**, honesty on impossible asks **0/4** — including suggesting the nonexistent "Wizarding World Goa" for RF-017. |
| **NEW** `eval/baselines/claude_sonnet_refinement.json` | Claude Sonnet answers gathered via fresh cold-context no-tools agents with zero access to the answer key (method documented in-file). Scores: verified-POI recall **0.979**, unverifiable rate **0.786**, strict honesty **0/4** — but with a critical, auditable nuance: all four impossible-ask answers *explicitly stated the interest cannot be served locally* before offering labelled alternatives (raw responses preserved in-file); no invented places anywhere. Any publication must state this distinction — the strict places-suggested metric undercounts Claude's verbal honesty. |
| **UPDATED** `eval/run_refinement_eval.py` + `eval/refinement_scoring.py` | `--results` rescore mode (re-score a saved run against a new baseline without re-running/re-paying) and baseline labelling from the file's `recorded_with` (report headings no longer hardcode "ChatGPT"). |
| **Verdict so far** | The wedge is **trust, not recall**: big chatbots beat the pipeline on naming famous places (1.00/0.98 vs 0.75 — with 3 fixable zero-cases dragging ours), but 75–79% of their suggestions are unverifiable against the truth-set, they don't say "no" when nothing real exists, and they have no itinerary follow-through (inclusion/stability don't exist for a chatbot answer). Kill/go decision deferred until the three recall bugs are fixed and the live run repeated. Comparison reports live in gitignored `eval/out/` (`report_vs_chatgpt.md`, `report_vs_claude_sonnet.md`) pending a deliberate publish. |

### v10.18.1 Changes (July 2026) — Live-eval shakedown fixes: dead google.api_core import was disabling live Gemini generation, chat_refine 503 retry, eval-runner resilience

The first `--live` run of the v10.18 eval immediately caught two real bugs — exactly what the harness is for.

| Change | Detail |
|---|---|
| **FIXED** `chains/itinerary_chain.py::_gemini_itinerary` | An unused `from google.api_core.exceptions import ServerError` import (a package google-genai does not depend on and which isn't installed) made the whole import block raise → misleading "google-genai not installed" → **every live Gemini itinerary generation silently fell back to the RAG fallback chain**. Caught by the eval's inclusion metric flatlining at 0.00 while refine/expansion worked. Import removed (the symbol was never referenced). |
| **FIXED** `chains/chat_refine_chain.py` | The known "no retry on transient Gemini 503s" gap (hit live 2026-07-12 and again killing the first live eval run): one cheap retry with 2s backoff on transient LLM errors (`_is_transient_llm_error` — 5xx/UNAVAILABLE/RESOURCE_EXHAUSTED/429 text match, version-proof against google.genai error-class churn). Non-transient errors still raise immediately. |
| **UPDATED** `eval/run_refinement_eval.py` + `eval/refinement_scoring.py` | Per-case retry (10s backoff) then record-as-errored instead of killing a 20-case live run on one persistent failure. Errored cases are **excluded from every aggregate but counted** (`n_errored`) and the report gains a "rerun before publishing" warning — fidelity claims never quietly average over cases that didn't run. |
| **FIXED** `chains/itinerary_chain.py` model fallback chain | Both hardcoded fallbacks were stale: `gemini-2.5-flash-lite-preview-06-17` is retired (404 NOT_FOUND) and — because 404 wasn't classified transient — it **raised out of the chain before `gemini-1.5-flash` (also retired) was ever tried**, so under primary-model congestion live generation always fell back to RAG. New `_classify_gemini_error()` routes failures three ways: transient (retry same model with backoff), model_missing (404 — skip straight to next fallback), fatal (auth/invalid — raise). Fallback list is now GA models `[settings.gemini_model, "gemini-2.5-flash", "gemini-2.0-flash"]`, deduped. |
| **Verified** | Full backend suite **207 passed** (200 + 7 new: transient-classifier ×3, gemini-error-classifier ×3, errored-aggregation ×1), 6 skipped. Offline eval gate still 1.000/100%. |

### v10.18 Changes (July 2026) — Refinement-Fidelity Eval Suite, the Phase 1 kill-criterion gate (GTM Phase 1, item 4)

Implements docs/GTM_STRATEGY.md §5 Phase 1 item 4: an automated, repeatable measurement of the v10.17 refinement pipeline's headline promise — a named interest becomes *verified* places that *actually appear* in the itinerary and *survive* further refinement — plus the apparatus for the published "WanderPlanner vs ChatGPT" comparison. Cost discipline: the default (regression) mode makes **zero** LLM calls and needs no network at all; the eval seeds a controlled truth-set into an **in-memory Qdrant** and never touches real ingested collections.

| Change | Detail |
|---|---|
| **NEW** `eval/refinement_fidelity_dataset.json` | 20 named-interest refinement cases: 16 positive (Harry Potter/London + Edinburgh, anime/Tokyo, zen gardens/Kyoto, Impressionist art/Paris, ancient Rome, Gaudí/Barcelona, Beatles/Liverpool, movie studios/LA, hawker food/Singapore, and an India-first block — Mughal Delhi, Bollywood Mumbai, Rajput Jaipur, Portuguese Goa, Sikh Amritsar, palaces-and-gardens Bengaluru) and 4 negative honesty cases where the correct answer is to pin nothing (HP in Goa, F1 in Jaipur, Ghibli in Amritsar, scuba in Kyoto). Fixtures = the controlled truth-set: 76 real OSM POIs (approx. real coords, incl. off-interest distractors per destination so precision is non-trivial) + 5 wiki chunks (exercising the wiki-only verification path, e.g. "Platform 9 3/4"). Each positive case also carries one invented candidate that MUST be dropped — the hallucination guard is scored, not assumed. `offline_candidates` replay a recorded interest-expansion so the deterministic stages run without any LLM. |
| **NEW** `eval/refinement_scoring.py` | Pure scoring shared by runner, baseline scorer and tests; name matching deliberately reuses `services/poi_pinning`'s `_normalize`/`_names_match` so the eval agrees with production about place identity. Per positive case: `expansion_recall`, `pin_recall`, `pin_precision`, `inclusion_rate` (pin appears **exactly once** with the `pinned` tag — the hard-constraint contract), `stability_rate` (pins survive an unrelated pace-change re-refinement — diff fidelity), composite `fidelity = 0.4·recall + 0.4·inclusion + 0.2·stability`. Negative cases: `honest` = zero pins AND no unverified candidate leaked into the itinerary. Baseline scoring for recorded ChatGPT answers: `verified_recall`, `unverifiable_rate`, honesty — same matcher, same truth-set. Markdown report renderer produces the vs-ChatGPT comparison table (the marketing artifact). |
| **NEW** `eval/run_refinement_eval.py` | Runner with two modes. **offline (default)** — deterministic + free: replays `offline_candidates` through the REAL `_apply_interest_pinning` → `verify_candidates` → `merge_pins` → `generate_itinerary` (mock LLM path, which honours pins) → pace-change regeneration; this is the regression gate and scores 1.000 by construction while the pipeline is intact. **--live** — real Gemini detection (`chat_refine`), expansion and generation for the actual kill-criterion numbers (~$0.02/case). Both modes force `qdrant_url=":memory:"` before any client is created and seed fixtures with zero-vectors (verification scrolls payloads; the embedding model never loads). `--baseline eval/baselines/chatgpt_refinement.json` scores recorded ChatGPT answers and emits the comparison. Reports land in `eval/out/` (gitignored; publish deliberately). Windows console UTF-8 reconfigure so ✅/❌ don't crash cp1252. |
| **NEW** `eval/baselines/chatgpt_refinement.template.json` | Recording protocol + ready-to-paste prompts (same trip framing the pipeline gets: destination + 5-day leisure + the refinement message). Founder records ChatGPT's first-answer place lists verbatim (fresh session per case, no cherry-picking), copies template → `chatgpt_refinement.json`, reruns with `--baseline`. |
| **NEW** `tests/unit/test_refinement_eval.py` | 23 fully offline tests. Dataset-consistency class runs every case through the REAL `verify_candidates_sync` against the dataset's own fixtures: all expected POIs verify (the eval's ceiling must be a perfect score), every invented candidate drops, negatives pin nothing, OSM pins carry fixture coords / wiki pins don't. Scoring math: exactly-once inclusion (duplicates fail), pinned-tag requirement, stability vs presence distinction, off-target precision, fuzzy title matching, negative honesty incl. leak detection, baseline recall/unverifiable-rate, aggregation + report rendering. Plus an RF-001 end-to-end offline slice (verify → mock generation → re-refinement → perfect score). |
| **Verified** | Full backend suite: **200 passed** (177 + 23 new), 6 skipped. Offline eval run end-to-end: 20/20 cases, fidelity 1.000 / honesty 100% (the deterministic ceiling — regressions in expansion wiring, verification, pin merging, prompt-block or mock-pin handling now surface as score drops). No frontend changes; `tsc` not applicable. **Next founder actions to produce the publishable numbers:** (1) run `--live` with a `GEMINI_API_KEY` (needs nothing else — fixtures are self-contained), (2) record the ChatGPT baseline per the template protocol, (3) rerun with `--baseline` and publish `eval/out/refinement_fidelity_report.md`. |

### v10.17 Changes (July 2026) — Refinement Hard-Constraints + Visible Diff UI, the "Harry Potter test" (GTM Phase 1, bet 2)

Implements docs/GTM_STRATEGY.md §2 product bet 2 — the #2 user-interview gap: refinements were prompt nudges, not commitments. Now "I'm a huge Harry Potter fan" becomes verified, hard-pinned places the itinerary *must* include, and every refinement that rebuilds the plan shows the user exactly what changed. Cost discipline: at most **one** extra small LLM call per refinement (only when an interest is actually named), verification is zero-LLM/zero-new-API (existing Qdrant collections), and the diff is computed client-side for free.

| Change | Detail |
|---|---|
| **NEW** `models/trip.py::PinnedPOI` + `TripConfig.pinned_pois` | Verified must-include place (name, lat/lon, poi_type, `source_interest`, `verified_by: "osm"\|"wiki"`), capped at `MAX_PINNED_POIS = 8` via a truncating validator (over-long client payloads degrade instead of 422ing). Mirrored in frontend `types/index.ts` + `tripConfigStore.ts` default. Only `services/poi_pinning.py` ever creates these — an unverified name can never become a pin. |
| **NEW** `chains/interest_expansion_chain.py` | `expand_interest_to_candidates(interest, destination)` — ONE `gemini-2.5-flash` call (same pattern as `extract_trip_chain.py`) turning a named interest into ≤10 candidate place names; explicitly instructed that invented names get discarded downstream so fewer-but-real beats many-but-fake. Best-effort: any failure → `[]`, refinement proceeds without pins. Deterministic canned expansions in mock mode. **Live-debugging note:** `gemini-2.5-flash` spends `max_output_tokens` on *hidden thinking before the visible JSON* — a 256 cap returned truncated JSON on every call (live-verified). google-genai 1.2.0 has no `thinking_budget` knob, so the cap is 2048 for now; when the dependabot bump to ≥2.x lands, add `ThinkingConfig(thinking_budget=0)` and drop the cap back to ~512. Same latent risk applies to `extract_trip_chain.py`'s 512 cap. |
| **NEW** `services/poi_pinning.py` | `verify_candidates_sync()` — verifies each candidate against `osm_pois` first (normalized exact/containment/`SequenceMatcher ≥0.80` fuzzy name match → pin carries the **canonical OSM name + real coordinates**), then `wiki` chunk text as an existence-only fallback (no coords; wiki scroll is lazy — skipped entirely when OSM covers everything). Unverified candidates are returned as `dropped`, never pinned — same "if OSM doesn't know it, we don't rank it" rule as `services/gems.py` (whose bounded `_scroll_destination` caps it reuses). Zero LLM calls, zero external APIs, pure CPU via `asyncio.to_thread`. `merge_pins()` — existing pins stay first (user commitments are stable), dedupe by normalized name, cap 8. |
| **UPDATED** `chains/chat_refine_chain.py` | Refine LLM now returns `named_interest` (prompt: detect fandom/passion/theme requests, do NOT name places yourself — the server verifies). New `_apply_interest_pinning()` orchestration: expand → verify → merge into `config_patch.pinned_pois`; reply gains an honest 📌 summary ("Pinned: X, Y — verified real places" / "couldn't verify Z, left it out" / "couldn't verify any, haven't pinned anything"). `ChatRefineResponse` gains `named_interest`, `pinned_pois` (newly verified only, for UI chips), `dropped_candidates`. **Integrity guard:** any LLM-authored `pinned_pois` in `config_patch` is stripped before parsing — pins can only come from verification. |
| **UPDATED** `chains/itinerary_chain.py` | New `_pinned_guidance_block()` → `PINNED MUST-INCLUDE PLACES — HARD CONSTRAINTS` prompt section (each pin: exact verified lat/lon or an explicit "coordinates not on file" instruction; `neutralize()`d) + a PINNED PLACES rules block ("non-negotiable, stronger than any other guidance; drop unpinned filler before dropping a pin; tag `pinned`"). Wired into **both** the Gemini and LangChain paths. `_mock_itinerary()` also honours pins (round-robin across days, `pinned` tag) so the whole loop is exercisable offline. |
| **NEW** `apps/web/lib/itineraryDiff.ts` | `diffItineraries(oldDays, newDays)` — added/removed/moved item detection matched by title similarity (normalized exact/containment/token-Jaccard ≥0.6 with stop-word filtering, so "Senso-ji Temple" ≡ "Visit Senso-ji Temple, Asakusa" across LLM runs). Pure client-side, O(old×new) over a few dozen titles. |
| **UPDATED** `ChatPanel.tsx` — in-place regeneration + visible diff | Replaces the old dead-end ("itinerary reset — open the wizard to regenerate"): refinements now rebuild in place via the existing `streamItinerary` SSE and post a **diff-chips message** in the Anya panel (green `+ added (Day N)`, red struck-through `− removed`, blue `↷ moved (Day A → B)`). Triggered when a patch lands `pinned_pois` (auto) or the user confirms a major regenerate. The old itinerary stays on screen until the new one arrives — a failed regeneration never destroys a working plan (error → chat notice, plan untouched). Input disabled + spinner note during rebuild. `ChatMessage.tsx` renders 📌 pin chips (hover shows OSM/Wikivoyage provenance) and diff chips; `chatStore.ts` messages carry optional `pins`/`diff` payloads. `ItineraryTimeline.tsx`: `pinned` tag renders as an amber 📌 badge (matching the 💎 pattern). |
| **NEW** `tests/unit/test_interest_pinning.py` | 29 fully offline tests: name normalization/fuzzy matching (incl. the ≥6-char containment guard so "eye" ⊄ "london eye"), OSM-match-gets-canonical-name+coords, wiki fallback, OSM-over-wiki priority, dedupe, merge order/cap, PINNED prompt-block formatting (coords vs "not on file"), mock expansion, and full `chat_refine` orchestration (pins land in patch, existing pins preserved, honest all-dropped reply, no-destination skip, LLM-patch integrity strip via non-interest path). |
| **Verified** | Backend suite: **177 passed** (148 + 29 new), 6 skipped; `tsc --noEmit` clean. **Live E2E** against the running Gemini-backed API (`POST /api/chat-refine`, "I am a huge Harry Potter fan…", London trip): `named_interest: "Harry Potter"` detected → expansion returned 9 real places (WB Studio Tour, Platform 9¾, Leadenhall Market, House of MinaLima…) → all honestly dropped against the empty local `:memory:` Qdrant with the "couldn't verify… better honest than invented" reply. The OSM-verified positive path is unit-proven; observing it live needs ingested `osm_pois` data + a signed-in session (same operational backlog item as the gems E2E). Web landing page loads with zero console errors. |

### v10.16 Changes (July 2026) — Hidden-Gem Scoring + Crowd Dial (GTM Phase 1, bet 1)

Implements docs/GTM_STRATEGY.md §2 product bet 1: itineraries can now surface community-verified, less-crowded places instead of only top-10-list output — the #1 gap from the July 2026 user interviews. Deterministic and zero-LLM by design: scoring is lexicon math over the already-ingested `reddit` + `osm_pois` collections, cached per destination, so the feature adds no per-request corpus scan, no added model calls, and ≤~250 prompt tokens.

| Change | Detail |
|---|---|
| **NEW** `services/gems.py` | `compute_gem_intel_sync()` — one bounded pass (≤300 POIs × ≤800 chunks) scoring OSM-verified POIs by Reddit community signal: mention count + Laplace-smoothed lexicon sentiment in a ±120-char window around each mention. Classification: 1–6 mentions + ≥0.55 sentiment → **hidden gem** (ranked by `sentiment / log2(2 + mentions)` — fewer mentions rank higher at equal praise); ≥12 mentions → **crowd favourite**; 0 mentions → excluded entirely (no community proof → never recommended; OSM presence alone is not a recommendation). Generic single-word names ("Park", "Beach") excluded from matching. `get_gem_intel()` — async wrapper with 24h in-process TTL cache + per-destination `asyncio.Lock` (stampede-safe under concurrency), compute offloaded via `asyncio.to_thread` per the v10.13 event-loop rule. `gem_prompt_block()` — dial-aware prompt formatting with provenance ("mentioned in N traveller post(s) on r/x, NN% positive sentiment"); returns "" for touristy/empty cases (zero token cost). |
| **NEW** `TripConfig.crowd_preference` | `"touristy" \| "balanced" \| "offbeat"` (default balanced) — backend `models/trip.py` + frontend `types/index.ts`/`tripConfigStore.ts`. Flows through the wizard's generic `config_patch` merge with no extra plumbing. |
| **UPDATED** `chains/itinerary_chain.py` | New `_gem_guidance_block()` (best-effort, `wrap_untrusted`-wrapped, empty for touristy/no-destination). `SYSTEM_PROMPT` gains a CROWD PREFERENCE rules block: offbeat builds days around gems (≤1-2 iconic anchors, avoids the CROWD-HEAVY list), balanced weaves in 1-2 gems, gems must use their provided OSM lat/lon, carry a `hidden_gem` tag, and include provenance in the description; the model may never invent a "hidden gem" not in the list. The three guidance blocks (itinerary examples, gems, budget) are now fetched via one `asyncio.gather` in both LLM paths — prompt assembly costs one round-trip, not three. |
| **UPDATED** `services/search.py` | `_CROWD_QUERY_EXPANSION` — the crowd dial now biases `retrieve_context()`'s vibe query (offbeat → "hidden gems off the beaten path quiet local secret underrated"; touristy → "top attractions iconic landmarks must-see famous"), same zero-infra mechanism as the persona/purpose expansions. |
| **UPDATED** `chains/wizard_chat_chain.py` | Anya now extracts `crowd_preference` as an optional field, with Hinglish-aware mappings ("hidden gems"/"less crowded"/"bheed nahi chahiye" → offbeat; "iconic places"/"must-see" → touristy) and a one-off Stage-2 checkpoint chip ("Crowd style? 🧭" → Iconic Spots 🗼 / Mix of Both ⚖️ / Hidden Gems 💎). **Live-verified** against the running Gemini-backed API: "less crowded hidden gems and peaceful places" → `config_patch.crowd_preference: "offbeat"`. |
| **UPDATED** frontend | `ItineraryTimeline.tsx`: `hidden_gem` tag renders as a violet 💎 badge (light+dark variants). `PaceBudgetSection.tsx` gains a 3-button crowd-style selector — note this section belongs to `WizardForm.tsx`, which is currently **not mounted anywhere** (legacy structured wizard; `LLMWizard` is the live path) — kept for parity if the form wizard is revived. |
| **NEW** `tests/unit/test_gems.py` | 15 fully offline tests (Qdrant scrolls mocked): gem/crowd/zero-mention/negative-sentiment classification, generic-name exclusion, fewer-mentions-rank-higher ordering, sentiment windowing, dial-aware prompt block (touristy empty, offbeat includes CROWD-HEAVY de-prioritisation), cache hit/expiry. Full unit suite green (148 passed); `tsc --noEmit` clean. |

### v10.15 Changes (July 2026) — Itinerary-Corpus Few-Shot Retrieval + Strategy Docs (GTM / Startup Re-Evaluation)

Completes the `itinerary-corpus-retrieval` roadmap item — the `itinerary_corpus` Qdrant collection (built in v10.12, ingest-only until now) is finally consumed at generation time: real traveller itineraries matching the user's trip shape are injected into the LLM prompt as few-shot grounding. Also lands the strategy documentation pass triggered by the first user-feedback interviews (July 2026): a new GTM strategy doc and a dated re-evaluation addendum correcting stale claims in the original startup evaluation.

| Change | Detail |
|---|---|
| **NEW** `services/search.py::retrieve_itinerary_examples()` | Retrieves up to 3 real traveller itineraries from `itinerary_corpus` per docs/rag-strategy.md §9: config-style query mirroring the ingest-side `_config_text()` embedding ("5 day moderate cultural couple trip Kyoto Japan"), searches **both named vectors** (`config` + `content`) with a destination payload filter plus a case-insensitive unfiltered fallback (the extraction LLM writes free-form destination strings; wrong-city docs are rejected client-side), merges 60% config / 40% content, weights by source-authority `quality_score` (× 0.5 + 0.5q), applies a 0.45 relevance floor, and formats each hit as `[Source: … — 5 days, moderate, cultural, couple]` + day-by-day lines. Helpers: `_corpus_config_query`, `_corpus_group_type` (GroupComposition → solo/couple/family/group), `_corpus_duration_days`, `_format_corpus_days_brief`. |
| **UPDATED** `chains/itinerary_chain.py` | New `_itinerary_examples_block()` (best-effort — any retrieval failure logs and degrades to the `"No reference itineraries available."` sentinel, never blocks generation; output `wrap_untrusted()`'d). `SYSTEM_PROMPT` gains a `REAL TRAVELLER ITINERARIES FOR REFERENCE` section + a `USING REAL TRAVELLER ITINERARIES` rules block (grounding for pacing/sequencing/same-day place groupings — "inspiration, not verbatim"). Injected in **both** the Gemini and LangChain (Groq/Ollama) paths. |
| **NEW** `core/config.py::itinerary_corpus_retrieval_enabled` (default `true`) | Feature gate; also added to `apps/api/.env.example` as `ITINERARY_CORPUS_RETRIEVAL_ENABLED`. |
| **NEW** `tests/unit/test_itinerary_corpus_retrieval.py` | 13 fully offline tests (embed + Qdrant mocked): config-query mirroring, group-type/duration mapping, 60/40 weighted-merge ordering, quality-score reranking at equal similarity, relevance-floor cutoff, disabled-flag and no-destination early exits, unfiltered-fallback wrong-city rejection, empty-days skip. Full unit suite green (133 passed). |
| **NEW** `docs/GTM_STRATEGY.md` | Full go-to-market plan + product roadmap: three product bets (crowd-aware "hidden gems" planning, refinement hard-constraints/"Harry Potter test", grounded inverse-plannable budgets), verified market landscape (Mindtrip acquired Thatch 2025; Sembark/TravClan prove Indian agents pay for software but aren't AI-native), GTM verdicts (offline travel agents = primary revenue engine; no creator marketplace), and a 3-phase roadmap with explicit kill/go criteria. |
| **UPDATED** `docs/STARTUP_EVALUATION.md` | Dated addendum (2026-07-11): corrections table for claims made stale by the auth-gate commits (accounts now mandatory → the central monetization blocker is gone; Booking Hub DPDP concern moot — localStorage only), first user-feedback findings, market updates, revised score 5/10 → 6/10 conditional. |
| **UPDATED** docs | `docs/rag-strategy.md` (v10.13 §9 retrieval-implemented note), `docs/system-design.md` (v8.4: §4 corpus few-shot retrieval block, §13 env var), `docs/itinerary-generation-flow.md` (corpus retrieval in the generation flow), extraction-chain docstring no longer says retrieval is pending. |

### v10.14 Changes (July 2026) — Mobile Responsiveness Overhaul + Anya Chat/Feasibility Bug Fixes + Generation Progress Streaming

Local-testing pass covering three threads: (1) a full mobile-responsive design review (`ui-ux-pro-max` skill) after the header was found overflowing on a 375px viewport, (2) a batch of real Anya wizard-chat bugs found by manually exercising budget/theme/pace/feasibility flows, and (3) the itinerary-generation loading experience going silent for 30–90s with no progress feedback.

| Change | Detail |
|---|---|
| **REMOVED** `components/common/MobileWarningBanner.tsx` | Dead-weight/contradictory now that mobile is an actively supported target, not just tolerated — deleted entirely (import + usage removed from `app/layout.tsx`, `overflow-x-hidden` added to `<body>` as a defensive guard against any remaining horizontal overflow). |
| **FIXED** header overflow on mobile | `LandingHero.tsx`: full wordmark + tagline + full-width "Plan a trip" button forced the header wider than a 375px viewport. Now icon-only logo + icon-only CTA below `sm:`, tighter padding/gaps, smaller hero heading. `UserMenu.tsx`: redundant "Log in" text link hidden below `sm:` (kept compact "Sign up" only). |
| **FIXED** signup/login footer link below the fold | `AuthLayout.tsx` (shared by signup/login/forgot-password/reset-password): reduced mobile-only vertical spacing (padding/margins/title size) so "Already have an account? Log in" is visible without scrolling on a 375×667 viewport (iPhone SE) — verified `scrollHeight === clientHeight`. |
| **CHANGED** Anya wizard modal backdrop | `LLMWizard.tsx`: flat solid `bg-black/50` (or fully white in light mode) replaced with a frosted-glass `bg-white/30 backdrop-blur-md dark:bg-black/30` so the blurred homepage stays visible behind the chat in both themes. |
| **FIXED** `FloatingAnyaButton` overlapping bottom mobile nav | Repositioned to `bottom-24` on mobile, `lg:bottom-6` unchanged on desktop. |
| **FIXED** Full Map View "✕ Close" button unreachable | `ThreeColumnLayout.tsx`: toolbar restructured into two rows (label + Close always visible; day-tabs independently horizontally scrollable) — previously a long day-tab row could push Close off-screen with no way back. |
| **FIXED** map/day/venue selection being non-intuitive | `ItineraryTimeline.tsx`'s `ActivityCard` is now clickable/keyboard-accessible — selecting an activity calls `setHoveredItem()` (existing map highlight/fly-to) **and** `setMobileTab('map')` (new shared state in `appStore.ts`) so mobile users land directly on the relevant map pin instead of manually switching tabs and hunting for it. |
| **FIXED** full-screen map centering on a random Indian town instead of the destination | `destination.lat/lon` is frequently `0/0` for multi-city/country-mode trips (never resolved at the top level). `MapWrapper.tsx` now prefers the first itinerary item's real resolved coordinates for centering, falling back to India-centre only as a last resort. Also added `RecenterOnChange` (`ItineraryMap.tsx`) since react-leaflet's `<MapContainer center>` prop only applies at initial mount — day switches previously did not re-center the map at all. |
| **FIXED** luxury/premium budget requests not recalculating | `core/budget_estimator.py`'s `PREMIUM_KEYWORDS`/`ECONOMICAL_KEYWORDS` now substring-match (e.g. "luxur" catches "luxurious") instead of requiring an exact keyword match. |
| **FIXED** theme chip groups only allowing single-select | Multi-select detection (`_is_multi_select_chips` backend, `_isThemeChipGroup` frontend) now excludes generic "No preference"-style chips before evaluating, so real multi-select theme groups (Culture/Food/Adventure/etc.) are correctly detected. |
| **NEW** general any-turn chip backfill | Previously the deterministic chip-backfill safety net only covered the very first "purpose" question — later fields like **pace** could render with zero chips if the LLM dropped them mid-turn. `wizard_chat_chain.py` now calls `_next_missing_field_prompt()` on *any* turn where `chips_list` is empty and the wizard isn't ready, backfilling just the chips (keeping the LLM's own wording) for both the JSON-success and plain-text-fallback response paths. |
| **FIXED** feasibility check surfacing too late with no explanation | `feasibility_chain.py`'s deterministic bare-minimum floor is now traveller-tier-aware (`_traveller_level_hint_text`); shortfall messaging surfaces earlier and states the reason. |
| **FIXED** "stuck at Generate itinerary" hang | LLM was hallucinating success/completion text without `ready_to_generate` ever becoming true (the `purpose` field was never actually captured). Added `_HALLUCINATED_GENERATION_RE` regex guard + `_next_missing_field_prompt()` helper, wired into both the JSON-success and plain-text-fallback response paths, to redirect the conversation back to the real next missing field instead of letting the wizard silently stall. |
| **NEW** progressively engaging generation loader | Previously `routers/itinerary.py` sent only 2 status messages ("Analysing your preferences...", "Searching destination content...") before going completely silent for the 30–90s LLM call. `_stream_generation` now runs `generate_itinerary()` as a background asyncio task while polling every 3s and streaming rotating filler messages (`_GENERATION_FILLER_MESSAGES`, e.g. "Planning day 1...", "Fetching local tips...", "Balancing your budget...") until the real result is ready. |
| **Verified** | Full backend suite: 153 passed, 6 skipped, 1 pre-existing unrelated failure (`test_signup_rejects_duplicate_email`), no new regressions. Frontend: 36/36 vitest passed, `tsc --noEmit` clean. Multiple Playwright mobile-viewport screenshot verifications (375px header, wizard modal light/dark backdrop, signup/login page fit at 375×667). End-to-end curl+cookie-jar test against the live Gemini-backed `/api/generate-itinerary` SSE stream confirmed the new rotating status messages (~42s generation, 8 messages shown). |

### v10.12 Changes (July 2026) — Itinerary Corpus Extraction Chain + `itinerary_corpus` Qdrant Collection

Second half of the `itinerary-corpus-scrapers`/`itinerary-corpus-extraction` roadmap items (docs/rag-strategy.md §9). Turns the raw content fetched in v10.11 into structured, retrievable documents. Retrieval (using this in the generation prompt) is still a separate, pending follow-up (`itinerary-corpus-retrieval`).

| Change | Detail |
|---|---|
| **NEW** `apps/api/chains/itinerary_corpus_extraction_chain.py` | `extract_itinerary_doc()` — one small Gemini call (`gemini-2.5-flash`, same JSON-extraction pattern as `chains/extract_trip_chain.py`) per raw document, returning a structured `ItineraryCorpusDoc` (destination/country/duration/pace/purpose/budget_tier/group_type/published_month/days) or `None` if the LLM determines the text isn't actually a day-by-day itinerary — fail-closed, never fabricates. `compute_quality_score()` maps source type + Reddit score to a 0–1 quality weight per the documented source-tier table (authoritative blogs/Wikivoyage 0.90, high-karma Reddit 0.85, standard Reddit 0.65, low-signal Reddit 0.40, YouTube 0.55). `ingest_itinerary_corpus()` orchestrates: fetch raw → extract → embed (config text + content text, two separate embeddings) → upsert. |
| **NEW** `itinerary_corpus` Qdrant collection | Uses **two named vectors per point** (`config` — destination+duration+pace+purpose+group_type text, matched against a user's trip config; `content` — full day-by-day text, matched by semantic similarity) rather than one, per the dual-embedding retrieval strategy in the design doc. `core/qdrant.py::_ensure_collections()` now creates it automatically alongside the existing single-vector collections. |
| **NEW** `core/config.py::qdrant_collection_itinerary_corpus` + `itinerary_corpus_refresh_days` (default 30) | New collection name setting + monthly ingestion cadence, matching the "Monthly: blog scrapers" cadence documented for this pipeline. |
| **NEW** scheduler job | `core/scheduler.py::_refresh_itinerary_corpus` — wired into `start_scheduler()` on a 30-day interval, tolerant of individual source/document failures (never crashes the scheduler thread). |
| **NEW** `apps/api/tests/unit/test_itinerary_corpus_extraction.py` | 17 fully offline tests (Gemini client, embeddings, and Qdrant all mocked) covering extraction success/failure/malformed-JSON/markdown-fence-stripping, quality scoring across all source tiers, config/content text construction, and full-pipeline orchestration. |
| **Verified** | Full backend suite: 154 passed (137 existing + 17 new), 6 skipped, no regressions. Manually verified the new Qdrant collection actually creates with the correct two-named-vector schema via an in-memory Qdrant client. |

### v10.11 Changes (July 2026) — Itinerary Corpus Scrapers (Phase 2, raw fetch only)

First step of the `itinerary-corpus-scrapers` roadmap item (docs/rag-strategy.md §9). Scope is deliberately limited to fetching raw, itinerary-shaped content from four free/keyless sources — no LLM structuring, no embeddings, no Qdrant writes yet (that's the separate downstream `itinerary-corpus-extraction` todo).

| Change | Detail |
|---|---|
| **NEW** `apps/api/scrapers/itinerary_corpus.py` | Four independent scraper functions, all free/keyless: (1) `scrape_travel_blog_feed` — Nomadic Matt + Planet D RSS via `feedparser`, full post body via BeautifulSoup, filtered to itinerary-shaped titles ("7 Day...", "...Itinerary", "...Trip Report"); (2) `scrape_wikivoyage_itinerary` — official Wikimedia `action=parse` API (not raw HTML scraping) against a curated list of dedicated Wikivoyage itinerary articles; (3) `scrape_reddit_trip_reports` — reuses the existing keyless direct public-JSON Reddit pattern (no PRAW/OAuth), searching itinerary-focused subreddits for itinerary-shaped self-posts; (4) `fetch_youtube_transcript` — `youtube_transcript_api` caption fetch for a curated seed list of video IDs (live video *discovery* would require the paid/keyed YouTube Data API, so kept out of scope). `collect_itinerary_corpus_raw()` orchestrates all four, tolerating individual source failures. |
| **NEW** dependencies | `feedparser==6.0.12`, `youtube-transcript-api==1.2.4` — both free, open-source, no API key. |
| **NEW** `apps/api/tests/unit/test_itinerary_corpus_scraper.py` | 16 fully offline tests (all HTTP/feedparser/YouTube calls mocked) covering title-shape filtering, per-source success/failure/edge cases, and orchestrator partial-failure tolerance. |
| **Scope note** | This module intentionally does not call any LLM or write to a vector store — see `itinerary-corpus-extraction` (next roadmap item) for structuring scraped text into the `ItineraryCorpusDoc` schema and populating the new `itinerary_corpus` Qdrant collection. |
| **Verified** | Full backend suite: 137 passed (121 existing + 16 new), 6 skipped, no regressions. |

### v10.10 Changes (July 2026) — Docker/Env Template Refresh + Supabase Production Runbook

Infra housekeeping pass covering the `docker-env-updates` and `db-hosting-config` roadmap items — no paid services introduced, everything uses each provider's free tier.

| Change | Detail |
|---|---|
| **CHANGED** `apps/api/.env.example` | Was missing ~25 settings `core/config.py` had grown to support since it was last updated (DB, JWT/auth, Google SSO, Resend email, OSM/retrieval flags, Reddit ingestion). Rewritten to document every setting with free-tier notes inline. |
| **FIXED** `core/config.py::database_url` default | Previously a non-functional placeholder Postgres string; now defaults to local SQLite (`sqlite+aiosqlite:///./dev.db`), matching how local dev actually runs — zero setup. |
| **NEW** `core/config.py::database_ssl_require` + `db.py` wiring | Supabase (and most managed Postgres) require TLS that `asyncpg` won't negotiate automatically from a bare connection string alone — previously undocumented. New boolean setting conditionally passes `connect_args={"ssl": True}` to the async engine. |
| **FIXED** cross-environment migration bug | `alembic upgrade head` against a brand-new SQLite database crashed on migration `0001` — `events.event_metadata` used a hardcoded Postgres-only `postgresql.JSONB()` with no SQLite fallback, while the ORM model (`db_models/event.py`) already had one (`JSONB().with_variant(JSON(), "sqlite")`). Fixed the migration to match. Verified: `alembic upgrade head` now runs `0001 → 0002 → 0003` cleanly end-to-end on a fresh SQLite file. |
| **FIXED** missing auto-migration on Railway deploy | `railway.toml`'s `startCommand` only ran `uvicorn` — a freshly provisioned Supabase database would have deployed with **zero tables** until someone manually ran migrations. Now `alembic upgrade head && uvicorn ...`. |
| **CHANGED** `docker-compose.yml` | Added an optional, profile-gated `postgres` service (`docker compose --profile postgres up`) for local Postgres-parity testing, without changing the SQLite-by-default path for everyone else. |
| **NEW** Supabase production setup runbook | `docs/system-design.md` §8A now documents: using the pooled connection string (port 6543, PgBouncer) instead of the direct one to avoid exhausting the free tier's 60-connection cap; the two required env vars; and the free-tier auto-pause-after-7-days-idle caveat. |
| **Verified** | Full backend suite: 121 passed, 6 skipped, no regressions. `alembic upgrade head` tested clean on a fresh SQLite file (previously broken). `docker-compose.yml` validated as syntactically correct YAML. |

### v10.9 Changes (July 2026) — Foreign-Currency Budget Input

Fixes an implicit, never-stated assumption: budget numbers were always treated as INR with no way for a user to state it in their own currency. This pass makes the INR assumption explicit and adds deterministic support for 10 common foreign currencies.

| Change | Detail |
|---|---|
| **NEW** `core/currency_convert.py` | `detect_foreign_currency(text)` — regex-based detection of an amount in one of `TOP_10_CURRENCIES = [USD, EUR, GBP, AED, SGD, AUD, CAD, JPY, THB, CHF]` (symbols like `$`/`€`/`£`/`¥` and keywords like "dollars"/"euros"/"dirhams", plus "2k" shorthand), explicitly excluding INR/₹/lakh/crore phrasing (handled by existing Section-2 rules). `get_conversion_rate(currency)` calls the free, keyless Frankfurter.app API (`GET /latest?from={cur}&to=INR`), cached 6 hours in-memory, falling back to a hardcoded approximate rate table on any failure. `convert_to_inr()` combines both into a full result dict. `currency_conversion_prompt_hint(text)` renders a ready-to-use, already-computed instruction for the wizard prompt — the LLM only phrases the conversion, never computes it (same architectural pattern as `core/budget_estimator.py`'s hints). |
| **CHANGED** `chains/wizard_chat_chain.py` | Field 4 (budget) now explicitly states "in ₹ (INR)" the first time it asks for budget, and names the 10 supported alternative currencies. A new `{currency_conversion_hint}` prompt section (injected every turn via `currency_conversion_prompt_hint(last_user_text)`) instructs Anya to use the exact deterministic conversion when present, storing `config_patch.budget.amount` in the converted INR figure and mentioning both the original and converted amounts + rate transparently. Mock/fallback budget-ask message updated to match. |
| **Verified** | Full backend suite: 121 passed, 6 skipped, no regressions. Frontend `tsc --noEmit` clean — no frontend changes were needed (purely backend/prompt logic; the currency conversion happens once at the point of user input, so INR remains the sole canonical currency everywhere downstream — feasibility check, budget estimator, itinerary generation, scoring). Live curl-verified: `"my budget is around $2000"` → `config_patch: {"budget": {"amount": 173000, "currency": "INR"}}`, reply states both `$2,000` and `₹1,73,000` + the rate; unrecognized currencies and INR-shorthand phrasing (`"1.5 lakh"`, `"₹50000"`) correctly do NOT trigger foreign-currency conversion. |
| **Not built this pass** | A currency-selector UI control (deliberately kept conversational/chat-based, consistent with the rest of the wizard — no new frontend component needed); support beyond the top 10 currencies (user is asked to restate in ₹ or a supported currency if an unrecognized one is mentioned). |

### v10.8 Changes (July 2026) — Real Deterministic Budget Estimator + Pre-Generation Feasibility Gate

Fixes a real bug reported live: when a user asked "what would this cost?" before specifying group size, the wizard quoted a flat number straight out of the Section 2 "Indian Cultural Context" budget-tier table (`"budget trip" = ₹40,000`) — a lookup table meant only for *parsing a user's own stated amount*, never for *recommending* one. It ignored group size entirely (no per-person split), destination cost tier, season, or traveller comfort level. This pass replaces that with a real, free-tools-only, deterministic computation, and closes a second gap: the LLM chat wizard (`LLMWizard.tsx`) had **no feasibility check at all** before auto-generating — only the older structured form (`WizardForm.tsx`) did.

| Change | Detail |
|---|---|
| **NEW** `core/budget_estimator.py` | Deterministic "bare minimum" budget engine — no LLM call, no paid API. `resolve_destination_tier()` classifies a destination as budget/moderate/premium via hand-authored keyword lists. `is_peak_season()` checks a generic Indian-holiday calendar plus a few destination-specific overrides. A hand-authored `_COST_MATRIX[tier][traveller_level]` (economical/mid_range/premium) gives per-person INR figures for round-trip flights, per-night stay, and per-day food. `parse_traveller_level()` reads the user's own wording ("economical"/"splurge"/etc.), defaulting to mid-range with an "assumed" flag. `estimate_bare_minimum_budget()` combines destination tier + season + group composition (adults/kids/seniors/infants) + duration + traveller level into `total_inr` / `per_person_inr` / a flights+stay+food breakdown — **and deliberately returns `None` if group size is completely unknown**, forcing every caller to ask a clarifying question rather than silently assuming 1 person. Supports **pre-booked overrides**: if a user says they've already booked flights/a hotel, `prebooked_flights_inr`/`prebooked_accommodation_inr` replace (not add to) the corresponding heuristic component. |
| **CHANGED** `TripConfig` | Added optional `prebooked_flights_inr` / `prebooked_accommodation_inr: int | None` fields, set when a user explicitly states an already-paid amount in chat. |
| **CHANGED** `chains/wizard_chat_chain.py` | Field 4 (budget) instructions rewritten: the flat Section 2 budget-tier table must **never** be used to *recommend* a number, only to *parse* a user-stated one. A new `{budget_estimate_hint}` block (rendered by `budget_estimate_prompt_hint()`) is injected every turn — it either instructs Anya to ask for group size first (if unknown) or supplies the real computed estimate + assumptions + a prompt to ask about already-booked flights/hotel if the user mentioned them. Verified live: with no group size given, the bot now asks "who will be joining you?" before quoting anything; once group size + comfort level are known, it correctly quotes a per-person **and** total figure (e.g. "₹2,42,300 total, about ₹80,800 per person... covers flights, stay, and food"). |
| **CHANGED** `chains/feasibility_chain.py` | `check_feasibility()` now also computes the deterministic `bare_minimum` via `estimate_bare_minimum_budget()`. `_build_response()` applies (a) pre-booked cost overrides (swaps the LLM's guessed flight/accommodation line for the user's real paid amount) and (b) a **deterministic floor** — `total = max(llm_estimated_total, bare_minimum_total)` — so "feasible" can never mean "feasible only per an overly optimistic LLM guess." Returns a new `bare_minimum_inr` field. Live-verified: Maldives, 2 adults + 1 kid, 6 days, ₹40,000 stated budget → correctly flagged infeasible, floor of ₹2,94,900 cited in the verdict, with cheaper domestic alternatives (Goa, Puducherry) still suggested. |
| **NEW pre-generation feasibility gate in `LLMWizard.tsx`** | The LLM chat wizard previously had **zero feasibility check** before auto-generating (only the older `WizardForm.tsx` + `FeasibilityCard.tsx` path did). Added `runFeasibilityGate()`: once the wizard's `ready_to_generate` fires, it calls `/api/feasibility-check` against the merged config first. If feasible, generation proceeds as before (1.2s delay). If not, generation is **paused** and a chat message shows the real shortfall + verdict + a "Set budget to ₹X" chip (using the deterministic `bare_minimum_inr`), a "Proceed anyway 🚀" chip (bypasses the LLM round-trip and calls `handleGenerate()` directly), and a "Let me adjust something else" chip. Any infra failure in the check itself silently falls back to the original auto-generate behavior (never blocks a trip on a hiccup). |
| **NEW comparison-mode budget parameter** | `services/comparison.py::_compare_bare_minimum_budget()` adds a real (not LLM-guessed) "Estimated Trip Budget (bare minimum)" row to destination comparisons, computed per-destination via the same estimator, with the cheapest destination marked as the winner. Returns `None` (parameter omitted) if group size is unknown for any destination — same never-guess-headcount rule. Verified in isolation (pre-existing, unrelated bug in `_compare_qualitative`'s `trip_config.dates.duration_days` — `dates` is a loosely-typed `dict` field, not a `TripDates` model — blocks the full `/api/compare-destinations` endpoint end-to-end today; out of scope for this pass, flagged for a follow-up fix). |
| **Verified** | Full backend suite: 121 passed, 6 skipped, no regressions. Frontend `tsc --noEmit` clean. Live curl-verified: wizard-chat budget hint (ask-first + per-person quote), feasibility-check (infeasible flag + floor + alternatives), and the isolated comparison-mode budget parameter (Goa ₹44,000 vs Maldives ₹1,60,000, Goa wins). |
| **Not built this pass** | Real per-day flights/accommodation scraping/API grounding (still Phase 3 of the earlier roadmap memo — this pass is entirely hand-authored heuristics, no external pricing calls); a UI budget-optimizer slider; re-wiring the feasibility gate into the edit-mode "change budget after itinerary generated" flow (flagged as a follow-up, not yet confirmed wired). |

### v10.7 Changes (July 2026) — Free-Tools Budget Curation (Phase 1)

Addresses two long-standing gaps called out in an internal design memo (`docs/rag-strategy.md` §9-12 roadmap): (1) `personas`/`purpose` had almost no code-level effect on the itinerary beyond a handful of hardcoded safety rules, and (2) budget had **zero real math** — costs were pure single-shot LLM guesses, and `scoring.py`'s `budget_score` was dead code hardcoded to `1.0`. This pass implements Phase 1 of the roadmap using **free tools only** (no paid pricing APIs) — Phases 2-5 (itinerary corpus scraping, real flight/hotel pricing APIs, a budget optimizer, and an agentic tool-calling router) remain a documented but unbuilt future roadmap.

| Change | Detail |
|---|---|
| **NEW** `core/budget_tiers.py` | Hand-authored persona/purpose → budget-tier lookup table (no ML). `luxury_traveller`/`budget_backpacker`/`senior_traveller` personas and `honeymoon`/`family_vacation`/`business_leisure`/`solo_backpacking`/`group_holiday`/`adventure` purposes each map to an accommodation-style + dining-weighting tier (persona takes priority over purpose). `resolve_budget_tier()` always returns a tier; `budget_tier_prompt_hint()` renders it (plus any splurge/save categories) as prompt-ready guidance text. |
| **NEW** `core/cost_grounding.py` | Free-tools-only cost grounding for the two most date-sensitive line items: (1) a haversine-distance-based flight cost **range** heuristic (5 distance bands, INR round-trip-economy ranges) using the trip's existing origin/destination lat/lon — no API call; (2) community-reported nightly-rate/price snippets pulled from the **already-ingested** `wiki`/`reddit` Qdrant collections via the existing `services.search.semantic_search()` — zero new scrapers or infra. Both are best-effort and degrade to an empty hint on any failure. |
| **CHANGED** `TripConfig` | Added optional `splurge_categories`/`save_categories: list[str]` fields (values from `["accommodation", "food", "activities", "shopping", "local_transport"]`), settable via the wizard or advanced UI, consumed by both prompt hints and scoring. |
| **CHANGED** `chains/feasibility_chain.py`, `chains/itinerary_chain.py` | Both prompts now inject a persona/purpose budget-tier hint and (itinerary chain only) flight/accommodation cost-grounding hints, computed via `asyncio.gather` with try/except fallback to an empty string so a RAG/lookup failure never blocks generation. |
| **FIXED** `chains/scoring.py` dead `budget_score` | Replaced the hardcoded `budget_score = 1.0` with a real `_budget_fit()` function: resolves the trip's budget tier, tags each candidate item against budget-leaning/premium-leaning vocabularies, and applies tier-fit and splurge/save-category bonuses/penalties (still a **tag-based proxy**, since `ItineraryItem` has no per-item cost field — real per-item cost scoring is a Phase 3+ item once real pricing data exists). |
| **NEW** persona/occasion query-expansion in `services/search.py` | `retrieve_context()`'s 3 RAG query variants are now biased with concrete persona/purpose keywords (e.g. `digital_nomad` → "coworking wifi cafe remote work", `honeymoon` → "romantic scenic couples sunset") so the *existing* wiki/reddit collections surface more persona-relevant content — no new Qdrant collection or payload schema needed (that's the unimplemented §11 unified metadata schema, still future work). |
| **NEW** wizard splurge/save chip | `wizard_chat_chain.py`'s optional-fields section adds a one-off "Want to splurge on anything? 💰" chip (Nice Hotel / Great Food / Top Activities / No preference) offered once all required fields + budget are known, writing to `splurge_categories`/`save_categories`. Non-blocking — never re-asked, never required. |
| **Verified** | Full backend suite: 121 passed, 6 skipped (no regressions in `test_scoring.py`/`test_rag.py` or elsewhere). Frontend `types/index.ts`/`tripConfigStore.ts` updated in lockstep (new fields + defaults) — confirmed type-safe (pre-existing, unrelated `next.config.ts`/module-resolution build issues in this environment are untouched by this change). |
| **Not built this pass (documented future roadmap)** | Itinerary corpus scraping (Phase 2), Amadeus flight pricing / Booking.com affiliate accommodation pricing (Phase 3), a "keep structure, swap tiers" budget optimizer + generated-itinerary learning flywheel (Phase 4), and an agentic tool-calling router for persona-verified venue selection (Phase 5) — see the design memo referenced in `docs/rag-strategy.md`. |

### v10.6 Changes (July 2026) — Admin Access Request/Approval Workflow

Closes a compliance/security gap: previously there was no controlled way for a second admin to be added post-launch other than a direct DB write, and nothing prevented ambiguity about whether new users could ever become admins by accident (they couldn't — `SignupRequest` never accepted `is_admin` — but there was no *positive* workflow for legitimately escalating a trusted user).

| Change | Detail |
|---|---|
| **NEW** `admin_requests` table | Migration `0003_admin_requests`. Tracks `user_id`, `status` (`pending`/`approved`/`rejected`), optional `message`, `reviewed_by`, `reviewed_at`. |
| **NEW** `POST /api/admin/requests` | Any authenticated non-admin can request admin access (optional reason message). Idempotent while pending; 400 if already an admin. |
| **NEW** `GET /api/admin/requests/me` | Requester's own latest request status, for account-page display. |
| **NEW** `GET /api/admin/requests` (admin-only) | List requests by status (default `pending`) — powers the `/admin` console's new "Admin access requests" panel. |
| **NEW** `POST /api/admin/requests/{id}/approve` \| `/reject` (admin-only) | Approve flips `is_admin=True` on the target user; reject leaves it unchanged. Both are one-shot (400 if the request was already reviewed) and both email the requester (`core/email.send_admin_request_decision_email`). |
| **NEW** admin notification emails | `core/email.send_admin_request_notification` emails every existing admin the moment a new request is created — dev-only log fallback when `RESEND_API_KEY` is unset, same pattern as password-reset. |
| **NEW** `/account` "Admin access" section | Shows a "Request admin access" button (hidden for existing admins), or "pending review" / "previously declined, request again" state, backed by `getMyAdminRequest()`/`requestAdminAccess()`. |
| **NEW** `/admin` "Admin access requests" panel | Lists all pending requests with requester name/email/message and Approve/Reject buttons; removes a request from the list immediately on action. |
| **Verified** | 8 new integration tests (`tests/integration/test_admin_requests.py`) covering creation, idempotent re-request, already-admin rejection, 401/403 gating, full approve→`is_admin=True`→admin-endpoint-access flow, reject→`is_admin` stays `False`, and double-review rejection. Full suite: 121 passed. Also live-curl-tested end-to-end against the running dev servers: signup → non-admin → request → visible to admin via `GET /admin/requests` → approve → confirmed `is_admin: true` on `/auth/me` → confirmed admin-endpoint access → cleaned up test user. |

### v10.5 Changes (July 2026) — Admin Console Entry Point

There was no way to reach `/admin` from the UI at all — admins had to know the URL. `UserMenu.tsx`'s dropdown now conditionally renders an "Admin console" link (with a shield icon) right above "Log out", only when `authStore.user.is_admin` is true. Non-admin users never see it.

### v10.4 Changes (July 2026) — Local Testing Bug Fixes: Auth Nav, Wizard Resume Race, Chip Backfill

Found and fixed during a full local manual-testing pass (real browser clicks + real Gemini API calls against `apps/api/dev.db`, not just automated fixtures):

| Change | Detail |
|---|---|
| **FIXED** no auth indicator in the app shell | There was no "Log in / Sign up" CTA on the home page, no way to tell if you were already signed in, and no way to sign out except by navigating directly to `/account`. Added `components/common/UserMenu.tsx` — an auth-aware nav control wired into `LandingHero`'s sticky nav, `ThreeColumnLayout`'s title bar, and `TopNav`. Shows "Log in"/"Sign up" when signed out; shows the user's name/email in a dropdown with "Account settings" + "Log out" when signed in. |
| **FIXED** wizard losing/duplicating context after auth redirect | `LLMWizard.tsx` had two mount-time `useEffect`s racing on the same `sessionStorage`-backed `pendingGeneration` flag — the "resume after auth" effect cleared the flag as a side effect, which broke the "bootstrap" effect's own guard check, causing both to fire and inject a stray fresh greeting on top of the resumed generation. Fixed by snapshotting `pendingGeneration` **once** via a lazy `useState` initializer shared by both effects, plus a `hasResumedGenerationRef` idempotency guard. |
| **FIXED** missing purpose chips on the very first wizard message | The Gemini-backed `wizard_chat()` path had no deterministic guarantee of chips on turn 1 (only the offline `_mock_wizard()` fallback did) — occasionally the LLM's first response omitted the mandated purpose chips (Leisure/Adventure/Honeymoon/etc.) despite the system prompt instructing "ALWAYS include chips when asking about purpose." Added a server-side safety net in `chains/wizard_chat_chain.py`: if `chips` is empty, `purpose` is still unfilled, and it's the first turn (`len(request.messages) <= 1`), deterministically backfill the standard 6 purpose chips. |
| **FIXED** SQLite FK cascade no-op during local testing | `apps/api/db.py` now sets `PRAGMA foreign_keys=ON` per-connection for SQLite only (no-op on Postgres/prod) — see Section 6A and `docs/scaling-tech-challenges.md` §7 for the full gotcha writeup. |
| **DEV-ONLY** password-reset link now logged locally | `apps/api/core/email.py` logs the actual reset URL when `RESEND_API_KEY` is unset, so the forgot-password flow can be tested end-to-end locally without a real email provider configured. Unreachable branch in prod (where `RESEND_API_KEY` is always set). |

**Verification:** `pytest -q` 113 passed / 6 skipped (backend, after both the SQLite and wizard-chain fixes); `tsc --noEmit` clean and `vitest run` 36 passed (frontend, after both the `UserMenu` and `LLMWizard` fixes); all fixes additionally live-tested against the running local dev servers (real signup/login/logout clicks, real `/api/wizard-chat` calls confirming chips now populate consistently across repeated first-turn calls).

### v10.3 Changes (July 2026) — Accounts, Auth Gate, Password Reset & Analytics

| Change | Detail |
|---|---|
| **NEW** Postgres auth/analytics foundation | Added async SQLAlchemy 2.0 ORM + Alembic migrations (`0001_auth_analytics`, `0002_password_reset`) and four core tables: `users`, `refresh_tokens`, `events`, `password_reset_tokens`. Production Postgres host is **Supabase**; local dev can use local Postgres or Supabase directly. |
| **NEW** authentication stack | Added email/password auth (Argon2id), Google OAuth 2.0 SSO, JWT access cookies, rotating opaque refresh cookies, `/api/auth/me`, logout, and self-delete. `POST /api/generate-itinerary` is now server-side gated by `get_current_user`. |
| **NEW** pending-generation resume | `LLMWizard.tsx` now persists the fully collected trip config to `sessionStorage` before redirecting signed-out users to `/signup`, then auto-resumes itinerary generation after signup/login/Google OAuth returns. |
| **NEW** password reset | Added `POST /api/auth/password/forgot` (always-200 anti-enumeration behavior), `POST /api/auth/password/reset`, hashed single-use reset tokens, and Resend-based delivery. Password reset revokes all existing refresh tokens for that user. |
| **NEW** consent + legal surface | Added `/terms`, `/privacy`, consent capture at signup, DPDP-aligned legal language, and `/account` self-delete UI with the "type DELETE to confirm" pattern. |
| **NEW** admin analytics backend | Added generic `events` table, `/api/admin/metrics/summary`, `/api/admin/metrics/timeseries`, and `/api/analytics/client-event`. Admin frontend dashboard remains in progress; Gemini token/cost tracking fields are scaffolded but the instrumentation is still being wired end-to-end. |

### v10.2 Changes (July 2026) — Brand Rename, Multi-City Reliability, Edit-in-Place, Dark Mode Everywhere

| Change | Detail |
|---|---|
| **REBRAND** WanderPlan → WanderPlanner | Every UI string, backend module, doc, and asset renamed across the codebase (55 tracked files), including `WanderplanLogo.tsx` → `WanderplannerLogo.tsx` and `docs/WanderPlan_PRD.pdf` → `docs/WanderPlanner_PRD.pdf` (regenerated). No functional change. |
| **FIXED** `chains/wizard_chat_chain.py` — multi-city drop | Field 2 (destination) only had 3 cases (single city / country-flexible / exploring) — no case for the user naming several explicit places (e.g. "Colombo, Mirissa, and Yala"), so the LLM silently kept only the first and dropped the rest. Added **Case D**: multiple named places → first becomes `destination`, rest become `hops` (itinerary generation already fully supported `hops`; the bug was purely upstream in extraction). `_summarise_state()` now also surfaces `hops` back to the LLM. |
| **FIXED** `chains/wizard_chat_chain.py` — country-mode never resolved to a real city | Naming a whole country (e.g. "Italy") set `destination_mode: "country"` but never resolved to a concrete `destination.city`, even after Anya proposed specific cities in her own reply — leaving budget/booking/travel-tips widgets blank downstream. Country mode is now framed as a momentary placeholder; the instant Anya proposes or the user confirms specific cities, `config_patch` resolves `destination_mode` to `"fixed"` with a real `destination` + `hops` (mirrors Case D). |
| **FIXED** `components/dashboard/Column1Metrics.tsx` / `components/itinerary/Column3Sidebar.tsx` | Both gated rendering of budget/expense/currency/travel-tips/booking-links widgets strictly on `destination?.city`, so any trip still in country-mode (or driven by the Anya wizard, which never populates the legacy `collectedLabels`) showed a blank left/right rail. Both now fall back to `destination_country` and gate on `hasDestination` (city OR country); `Column1Metrics` shows a "City +N" label for multi-hop trips. |
| **REDESIGNED** `components/itinerary/PolaroidCard.tsx` | Replaced the oversized full-width 16:9 hero-video card with a compact horizontal layout (small 80–96px thumbnail + text side-by-side) so the itinerary text is immediately scannable instead of being pushed below a huge video. Added an `onError` handler (`imgFailed` state) so a thumbnail URL that later 404s falls back to the gradient placeholder instead of a broken-image icon. |
| **FIXED** YouTube thumbnail reliability | `app/api/youtube-thumbnail/route.ts` scrapes youtube.com search HTML (no official API key) and is inherently flaky — confirmed the *same query* failing then succeeding seconds later. Two client bugs turned rare blips into permanent blanks: the `useThumbnail` hook cached `null` on any failure (poisoning that query for the session) and had no retry. Fixed: only cache genuine hits, retry up to 3x with backoff (500ms/1000ms). Server route also pins `gl=US&hl=en&persist_gl=1` and pre-sends the EU consent cookie to avoid landing on a GDPR interstitial page with no embeddable `videoId`. |
| **FIXED** theme multiselect regression | The wizard decided whether a chip group (Culture/Food/Adventure/etc.) was multi-select by pattern-matching chip text against a hardcoded keyword list on the frontend — fragile, since Gemini freely generates the exact chip wording each turn, so any phrasing drift silently degraded multiselect to submit-on-first-click. Backend now computes a `multi_select` boolean deterministically (`_is_multi_select_chips()`) and returns it explicitly in the `wizard-chat` response; the frontend trusts that flag (old heuristic kept only as a fallback for stale/cached messages). |
| **ADDED** dark/light `ThemeToggle` on itinerary page + chat panel | `ThemeToggle` previously only existed on the shared `/t/[slug]` read-only page — there was no way to switch themes from the main dashboard or an open Anya chat. Component now accepts a `className` override and is wired into `ThreeColumnLayout`'s title bar and `ChatPanel`'s header. |
| **FIXED** "Edit Trip" losing all context | The Column-1 "Edit Trip" button called `openWizard()` with no preload, so Anya restarted the entire conversation from scratch even though a complete config + generated itinerary already existed for the session. `LLMWizard.tsx` now detects edit mode (existing itinerary + fully populated config, no fresh preload) and seeds `partialConfig` from the current config (`_checkpoint_asked: true`), greeting with a trip summary and "Change destination/dates/budget/themes" / "Regenerate as-is" chips instead of re-asking everything. Backend Stage-3 generate-signal trigger phrases widened to recognize "regenerate"/"update it" wording natural to editing. |

**Verification:** backend syntax-checked (`python -c "import chains.wizard_chat_chain"`) and live-curl-tested against a running instance for Case D, country-mode resolution, the `multi_select` flag (theme chips → `true`, single-choice chips → `false`), and the edit-mode "change budget → regenerate as-is" flow (`ready_to_generate: true` confirmed with realistic post-generation dates). Frontend `tsc --noEmit` clean after every change.

### v10.1 Changes (July 2026) — Wizard Reliability + Visual PDF Export

| Change | Detail |
|---|---|
| **UPDATED** `chains/wizard_chat_chain.py` | `max_output_tokens` 800 → 2048 (was truncating longer replies mid-sentence); new `_looks_like_valid_json()` gate + retry loop (up to 3 attempts) on incomplete/truncated Gemini JSON instead of falling straight to salvage-text mode; new `_strip_trailing_json_artifacts()` (trims stray trailing JSON punctuation) and `_strip_leaked_schema_tail()` (strips cases where Gemini emits valid JSON but echoes the remaining schema keys, e.g. `"chips": [], "config_patch": {}...`, literally inside the `reply` string) — both applied on the happy path and the fallback path. |
| **UPDATED** `components/wizard/LLMWizard.tsx` | `readyToGenerate` now derives solely from the backend's explicit `summary !== null` signal instead of a local required-field counter, so the chat input stays visible through Stage-2 optional follow-ups (e.g. "add departure city") instead of disappearing once the 6 required fields are filled. Added `THEME_CHIP_KEYWORDS` heuristic + `_isThemeChipGroup()` so theme chip groups (Culture/Food/Adventure/etc.) toggle multi-select with a "Continue ✓" button instead of submitting on the first click; other chip groups still submit instantly. |
| **REWRITTEN** `components/pdf/ItineraryDocument.tsx` | Itinerary PDF export redesigned to a colorful travel-journal "scrapbook" layout (per user-supplied reference PDF): 7-color pastel palette cycling per day card, breadcrumb + bold day titles, bold-label bullets, booking-link preview chips, transit-warning boxes; matching card treatment for Trip Essentials / Visa & Safety / Cost Breakdown / Packing Checklist. Emoji, arrows (→/↑), and ≈ replaced with ASCII-safe equivalents — react-pdf's base Helvetica font has no glyphs for them. |
| **NEW** `services/pexels.py` | Async Pexels API client — `get_day_photo()` / `get_day_photos()`, in-memory query cache (500 entries), fully best-effort (missing key / network failure / timeout / empty results all degrade silently to `None`). |
| **UPDATED** `chains/itinerary_chain.py` | After day scoring, concurrently fetches one Pexels photo per day (`"{destination} {day theme}"` query) with a 6s total timeout budget before building the `ItineraryResponse`; failures never block itinerary generation. |
| **UPDATED** `models/itinerary.py` / `apps/web/types/index.ts` | `ItineraryDay` gains optional `image_url`, `image_photographer`, `image_photographer_url` fields, rendered as a hero photo + attribution in the PDF. |
| **NEW** `core/config.py` setting / `.env.example` | `pexels_api_key: str = ""` / `PEXELS_API_KEY=` — optional; app runs normally without it (no photos, no errors). |

**Verification:** backend syntax-checked and live-curl-tested against a running instance for each fix (confirmed clean departure-city reply, confirmed `ready_to_generate` stays `false` through Stage 2); frontend `tsc --noEmit` clean; live Pexels API call tested directly; full test PDFs rendered (`@react-pdf/renderer` → PNG via PyMuPDF) and visually compared against the reference layout.

### v10.0 Changes (July 2026) — Security Hardening

Addresses 9 of the 10 findings in `docs/scaling-tech-challenges.md` §1 (status detail: §1a of that doc). Auth (#1) explicitly deferred as a larger, separately-tracked effort.

| Change | Detail |
|---|---|
| **NEW** `core/rate_limit.py` | slowapi `Limiter` (IP-keyed, in-memory): `10/minute` on all LLM-backed endpoints (`chat`, `chat-refine`, `wizard-chat`, `recommend-cities`, `feasibility-check`, `compare-destinations`, `generate-itinerary`, `extract-trip`, `share`), `30/minute` default elsewhere. Single-instance only — Redis-backed limiting still required before horizontal scaling. |
| **NEW** `core/errors.py` | `sanitize_error(exc, context)` — logs full exception server-side, returns a generic message + short reference id instead of `str(exc)` in HTTP 500 bodies. |
| **NEW** `core/prompt_guard.py` | `neutralize()` (redacts injection phrases like "ignore previous instructions") + `wrap_untrusted()` (fences untrusted text behind explicit "this is DATA, not instructions" delimiters). Applied to RAG-retrieved context, extract-trip fetched/pasted text, chat messages, and trip-config JSON across `chat_chain.py`, `chat_refine_chain.py`, `feasibility_chain.py`, `recommend_cities_chain.py`, `itinerary_chain.py`. Defense-in-depth, not a hard-blocking classifier (false-positive risk on legitimate travel content). |
| **NEW** `core/logging_config.py` | `configure_logging()` — structured JSON logging + `RedactionFilter` (redacts emails, API keys, phone numbers). All `print()` calls in `travel_tips.py`, `scheduler.py`, `recommend_cities_chain.py`, `itinerary_chain.py` replaced with `logger.*`. |
| **NEW** `apps/web/lib/url-safety.ts` | `isSafeExternalUrl()` — only allows `http(s)` URLs with a hostname; blocks `javascript:`/`data:` URIs in LLM-generated `booking_url` before rendering as a clickable link (`ItineraryTimeline.tsx`). |
| **FIXED** SSRF in `chains/extract_trip_chain.py` | DNS-resolves the hostname and rejects private/loopback/link-local/reserved/multicast IPs (blocks cloud metadata IP `169.254.169.254`); manually walks redirects (max 3 hops, re-validated per hop); caps response to 2MB; restricts content-type to `text/html`/`text/plain`. |
| **UPDATED** `routers/share.py` | Slug generation changed from `uuid4().hex[:8]` (32-bit) to `secrets.token_urlsafe(16)` (128-bit); both endpoints rate-limited. |
| **UPDATED** `main.py` | `allow_credentials=False`; slowapi middleware + exception handler wired in; `configure_logging()` called at startup. |
| **UPDATED** `core/config.py` | New `field_validator` on `allowed_origins` rejects `"*"`. |
| **UPDATED** `requirements.txt` / `requirements-dev.txt` | `slowapi==0.1.10` added; `google-genai` pinned to `1.2.0` (was `>=1.0.0`); `pip-audit==2.7.3` added. |
| **NEW** `.github/dependabot.yml` | Weekly pip (apps/api), npm (apps/web), github-actions dependency update PRs. |
| **NEW** `.github/CODEOWNERS` | Requires review on `**/AGENTS.md`, `**/CLAUDE.md`. |
| **UPDATED** `.github/workflows/ci.yml` | New wildcard-`ALLOWED_ORIGINS` check, `pip-audit` step (advisory — surfaced 23 pre-existing transitive CVEs unrelated to this change, e.g. in `starlette`/`python-multipart`/`urllib3`/`lxml`), new `agent-instructions-changed` job that warns on PRs touching AGENTS.md/CLAUDE.md. |

**Regression testing:** full backend pytest suite (89 passed / 6 skipped), frontend `tsc --noEmit` (clean) + vitest (36 passed), and live smoke tests of every modified endpoint in mock mode (SSRF block confirmed, rate-limit 429s confirmed after 10 requests/min, share token format confirmed, sanitized error responses confirmed) — no regressions found.

### v9.0 Changes (July 2026) — RAG Optimization Round 2

#### New RAG Capabilities
| Change | Detail |
|---|---|
| **NEW** `services/hyde.py` | HyDE query augmentation — template-based hypothetical passage generator (persona/pace/purpose aware), applied to the "vibe" query variant only, no extra LLM call |
| **UPDATED** `services/search.py` | Hybrid search: BM25 (`_bm25_search_collection_sync`, Qdrant scroll + `rank_bm25.BM25Okapi`) fused with semantic cosine search via existing RRF, applied to every `semantic_search()` call; added `_rerank()` cross-encoder step (fail-safe) and `enable_reranking` override param on `retrieve_context()` |
| **NEW** `scrapers/osm.py` | Overpass API POI ingester — geocodes destination, queries ~14 POI categories in a radius, dedupes, builds embeddable descriptions, upserts to new `osm_pois` collection |
| **NEW** `services/itinerary_cache.py` | Tier-1 fallback — caches successful itineraries keyed by `embed(dest+duration+pace+purpose)`, read back via cosine ≥ 0.88; strips fallback markers before storing to prevent cache-poisoning |
| **NEW** `services/rag_fallback.py` | Tier-2 fallback — builds a real itinerary purely from ingested OSM POIs (no LLM), declines (returns `None`) if fewer than 3 POIs exist for the destination |
| **UPDATED** `chains/itinerary_chain.py` | New `_fallback_itinerary()` 3-tier chain (cache → RAG skeleton → enhanced mock with spliced-in real tip text); wired into `generate_itinerary()`'s exception path; cache-store-on-success wired into the happy path |
| **UPDATED** `core/scheduler.py` | New weekly OSM POI refresh job iterating `KNOWN_DESTINATIONS` with a polite delay between Overpass calls |
| **UPDATED** `core/config.py` | New settings: `hybrid_search_enabled`, `hyde_enabled`, `reranking_enabled` (default `False` — scoped on, see below), `qdrant_collection_itinerary_cache`, `itinerary_cache_score_threshold`, `reranker_model`, `osm_overpass_url`, `osm_poi_radius_m`, `osm_poi_max_results`, `osm_refresh_days`, `osm_ingest_delay_seconds` |
| **FIXED** concurrency bug | Blocking `embed()`/Qdrant `.search()`/`.scroll()` calls were invoked directly inside `async def` functions, so `asyncio.gather()` over the 3 query variants never actually ran in parallel. Fixed via `asyncio.to_thread()` on every blocking call, plus batching all 3 query embeddings into a single `embed()` call. Throughput ~10 → ~23.6 req/s @ concurrency=50 (measured via new `load_test_rag.py`) |
| **NEW** `apps/api/eval/golden_dataset.json` + `run_rag_eval.py` | Golden dataset for automated retrieval evaluation — Precision@k/Recall@k/MRR/nDCG@k. Current: Recall@10=1.00, MRR≈0.85–0.94, nDCG@10≈0.89–0.96 |
| **NEW** `apps/api/load_test_rag.py` | Concurrent-request load test tool for measuring retrieval throughput/latency |

**Design decision — reranking scoped, not global:** cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`) is disabled by default (`settings.reranking_enabled=False`) and explicitly enabled (`enable_reranking=True`) only at the two true LLM-generation call sites in `chains/itinerary_chain.py`. Enabling it globally dropped load-test throughput from ~23.6 to ~7 req/s @ concurrency=50; scoping it to itinerary generation (where LLM latency already dominates) recovered throughput to ~13.5 req/s for all other RAG callers while keeping the precision benefit where it matters most.

### v7.0 Changes (June 2026)

#### Wizard End-to-End Fixes
| Change | Detail |
|---|---|
| **UPDATED** `chains/wizard_chat_chain.py` | Prompt v5, temperature 0.4, max tokens 800, 3-attempt exponential-backoff retry on 503/429/UNAVAILABLE, smart mock fallback that reads `partial_config`, and JSON-wrapped assistant history with real `config_patch` |
| **UPDATED** `models/chat.py` | `ChatMessage` now includes `config_patch: dict = {}` so assistant history can carry real extraction state |
| **UPDATED** `components/wizard/LLMWizard.tsx` | Frontend message objects now store `config_patch`; assistant history includes it; `allFilled` now uses the same `_isFieldFilled` logic as the tab indicators |
| **UPDATED** `lib/api.ts` | Wizard message request typing includes `config_patch`; `streamItinerary` docs aligned with `res.ok` / `NO_DATA` guard fixes |
| **UPDATED** wizard history guards | Raw JSON leak prevention tightened (`or raw` → `or ""`) and double-wrapped JSON detection added before replaying assistant history |

### v6.0 Changes (June 2026)

#### Anya Prompt v3 + Wizard Flow
| Change | Detail |
|---|---|
| **UPDATED** `chains/wizard_chat_chain.py` | System prompt rewritten to v4: persona-first (Anya is a travel professional, not a slot-filling agent), new §1a Absolute Speaking Rules with WRONG/RIGHT examples, `thought_process` field removed, output schema reframed as "phone call speech" |
| **REMOVED** `thought_process` field | Eliminated from `WizardChatResponse`, system prompt, and API contract. Added `_strip_leaked_reasoning()` as last-resort safety net. |
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

---

### v10.13 Changes (July 2026) — Local Testing Bug Fixes: Event-Loop Hangs, Budget Feasibility, Google SSO Gating, Duplicate Keys, Generation Watchdog

A round of fixes surfaced during a live local walkthrough of signup, the Anya wizard, and itinerary generation — no new features, all correctness/reliability fixes.

| Change | Detail |
|---|---|
| **FIXED** signup/all-requests hang | `core/embeddings.py`'s `embed()`/`rerank_scores()` were being called **synchronously** inside async request handlers and a background `asyncio.create_task` (Reddit seeding at startup) — a CPU-bound SentenceTransformer/CrossEncoder call run inline blocks the single-threaded asyncio event loop for its entire duration, freezing *every* concurrent request including signup. Fixed by wrapping every call site in `asyncio.to_thread(...)`: `scrapers/reddit.py`, `routers/reddit_highlights.py`, `scrapers/wikivoyage.py`, `scrapers/osm.py`, `chains/itinerary_corpus_extraction_chain.py` (the two search-path call sites in `services/search.py` already did this correctly and were the reference pattern). |
| **FIXED** backend crash introduced by the above fix | Once `embed()`/`rerank_scores()` ran on a background thread, the process began crashing intermittently — PyTorch's MPS (Apple Metal GPU) backend is not thread-safe when invoked off the main thread. Fixed by forcing `device="cpu"` explicitly in both `get_embedder()` and `get_reranker()` in `core/embeddings.py`, since on a dev laptop the CPU is fast enough for this workload and thread-safety matters more than the marginal MPS speedup. |
| **FIXED** Anya not flagging an infeasible budget the user *lowers* mid-conversation | `budget_estimate_prompt_hint()` (deterministic bare-minimum, `core/budget_estimator.py`) was already computed every turn once group size is known, but the wizard system prompt in `chains/wizard_chat_chain.py` scoped it to "only relevant if user asks for a recommendation" — so if a user stated or reduced their own budget, the LLM had no instruction to compare it against the floor. Added a "FEASIBILITY CHECK" instruction block (Field 4/budget section) directing the LLM to always compare a user-stated/reduced budget against the computed bare-minimum and proactively flag any shortfall, renaming the section header from "BUDGET RECOMMENDATION HINT" to "BUDGET GUIDANCE HINT" to reflect its now-dual purpose. |
| **FIXED** literal `\u20b9` (₹) escape shown in chat text | When Gemini's wizard-chat response failed the strict JSON-validity check, the code fell back to a best-effort plain-text extraction path that never ran the response through `json.loads` (which normally auto-decodes `\uXXXX` escapes) — so literal escape sequences leaked into the UI. Added `_decode_stray_unicode_escapes()` in `chains/wizard_chat_chain.py`, applied on the plain-text fallback path (primary fix) and defensively on the successful-JSON path too (in case of double-escaping). |
| **NEW** `GET /api/auth/config` + conditional Google SSO button | Google SSO returning `{"detail":"Google sign-in is not configured."}` in local dev is expected (blank `GOOGLE_CLIENT_ID`/`SECRET`), not a bug — but showing a dead "Continue with Google" button was a poor look either way. Added a new backend endpoint returning `{"google_sso_enabled": bool(settings.google_client_id)}`, a `fetchAuthConfig()` helper in `lib/authApi.ts` (fails closed to `false` on any error), and a new `components/common/GoogleSsoSection.tsx` that fetches this flag and only renders the Google button + "or" divider when enabled. `app/signup/page.tsx` and `app/login/page.tsx` now use this component instead of the raw button + manual divider. |
| **FIXED** wizard-chat/extract-trip false-positive "Connection error" | `lib/api.ts`'s shared axios client used a flat 25s timeout for every endpoint, but the backend's own Gemini retry logic for `/api/wizard-chat` and `/api/extract-trip` (up to 3 attempts on JSON-validity failures, with backoff) can legitimately take longer than 25s in the worst case, racing the frontend timeout and surfacing a spurious network-error toast on an otherwise-still-working request. Added a per-call `{ timeout: 45_000 }` override for both endpoints; the shared 25s default is unchanged for lighter endpoints. |
| **FIXED** duplicate React key warnings/render glitches in the wizard chat (`llm-msg-N`) | `components/wizard/LLMWizard.tsx` generated message ids from a **module-level counter** (`let _msgId = 0; const nextId = () => \`llm-msg-${++_msgId}\``) — this counter resets to 0 whenever Next.js Fast Refresh re-evaluates the module in dev, while the component's already-rendered message list (which Fast Refresh preserves) keeps its old ids, so new messages after any hot-reload collide with existing ones (`llm-msg-2`, `llm-msg-9`, etc. — the "44 issues" the user saw in devtools). Replaced with `crypto.randomUUID()` (with a `Date.now()`+`Math.random()` fallback for older environments), which never depends on any module-level state and can't collide across reloads. |
| **CHANGED** signup error message specificity | `POST /api/auth/signup` previously returned the same generic `"Unable to sign up with these details."` whether or not the email was already registered, as an account-enumeration mitigation. Per explicit product decision this session, changed to an actionable `"An account with this email already exists. Try logging in instead."` — trading a small amount of enumeration resistance for a materially better signup UX. Login's `"Incorrect email or password."` (already deliberately non-specific about *which* part is wrong, to avoid confirming registered emails at login time) was left unchanged. Both messages flow to the UI unmodified via `authErrorMessage()` in `lib/authApi.ts`, which surfaces `err.response.data.detail` verbatim — no frontend changes were needed. |
| **NEW** generation-stall watchdog in the wizard UI | Root-caused a report of the wizard getting stuck showing "Starting up…" indefinitely: if the `/api/generate-itinerary` SSE stream dies with total silence (dropped connection, or in dev, a Fast Refresh remount aborting the underlying `fetch` — `streamItinerary()`'s catch handler deliberately ignores `AbortError` so a normal wizard-close doesn't show a spurious error, but this also meant a genuine silent death was indistinguishable from an intentional cancel), the UI had no way to detect "nothing is happening" and stayed frozen forever. Added a client-side watchdog timer in `startGeneration()` (`components/wizard/LLMWizard.tsx`), re-armed on every `status` SSE event, that fires after **60 seconds of total silence**: cancels the stream, shows `"Generation is taking much longer than expected and may have stalled. Please try again."`, and returns the user to the chat phase so they can retry immediately instead of waiting indefinitely. Cleared on unmount alongside the existing stream-cancel cleanup. |
| **Verified** | Direct backend calls confirmed: signup returns in ~90ms even under concurrent load post-fix; concurrent embed+signup calls no longer crash the process; Anya correctly warns when a stated budget (e.g. ₹1,20,000) is below the computed bare-minimum (e.g. ₹2,42,300); `_decode_stray_unicode_escapes()` unit-verified on `\u20b9` → ₹; `/api/auth/config` returns `{"google_sso_enabled": false}` locally with no Google button rendered; a direct `/api/generate-itinerary` call completed successfully end-to-end in ~46s; `npx tsc --noEmit` clean after all frontend changes; both dev servers picked up every change via hot-reload with no manual restarts needed. |

---

## 15. Pending Roadmap Items (as of v10.12)

Tracked backlog items not yet implemented. All are believed achievable with free tools only, except the one explicitly blocked below. Full context for each lives in `docs/rag-strategy.md` (sections referenced inline).

| ID | Item | Description | Status |
|---|---|---|---|
| `itinerary-corpus-retrieval` | Wire itinerary corpus into generation prompt | Retrieve 2–3 matching real itineraries from the new `itinerary_corpus` Qdrant collection (built in v10.12) and inject them as few-shot grounding examples in `chains/itinerary_chain.py`'s system prompt. Depends on `itinerary-corpus-extraction` (done). | ✅ Done (v10.15) — `services/search.py::retrieve_itinerary_examples()` |
| `corpus-source-attribution-ui` | Source-attribution UI | Once corpus grounding is live, show a small "Inspired by trip reports from r/solotravel and Nomadic Matt"-style attribution note in the itinerary UI — a key differentiation/marketing signal for "curated, not generic" positioning. Depends on `itinerary-corpus-retrieval`. | Pending |
| `agentic-router-tool-calling` | Lightweight agentic router / tool-calling layer | Per docs/rag-strategy.md §12: introduce tool-calling for persona-specific verified venue selection (dog-friendly, coworking, romantic dining), reusing the free OSM Overpass API already used elsewhere. Also becomes the primitive the budget optimizer (below) uses for line-item swaps. | Pending |
| `budget-optimizer-pass` | Keep-structure budget optimizer pass | Tool-calling-based optimizer that re-scores existing itinerary line items (accommodation/activities/dining) against cheaper/pricier alternatives within the same theme/day-structure, instead of a full regeneration. Add a budget-slider UI showing a diff of what changed. Depends on `agentic-router-tool-calling`. | Pending |
| `generated-itineraries-tracking` | `generated_itineraries` quality-signal tracking (Phase 4) | Per docs/rag-strategy.md §10: store `persona_fingerprint` + implicit quality signals (regenerated, session duration, shared, chat-refine turns) for every generated itinerary once there is real production traffic — pure DB/analytics instrumentation, no paid API. | Pending |
| `generated-itineraries-retrieval` | Wire `generated_itineraries` flywheel into retrieval | Once ~50–100 quality-scored itineraries exist (via the tracking item above), retrieve similar high-quality past itineraries as a second few-shot source alongside the itinerary corpus. Depends on `generated-itineraries-tracking`. | Pending |
| `booking-accommodation-pricing` | Booking.com affiliate pricing for accommodation costs | Booking.com's affiliate program is free-to-join (no per-call cost), but requires partner account approval — a paid/approval-gated dependency, not achievable purely with free/keyless tools right now. Fallback if unblocked later: use community-reported nightly rates from the same free corpus sources as `itinerary-corpus-scrapers` rather than a paid hotel-price API in the meantime. | **Blocked** — requires Booking.com affiliate partner account, skipped per "free tools only" constraint |

**Completed this session (for context):** `docker-env-updates`, `db-hosting-config`, foreign-currency budget input, `itinerary-corpus-scrapers` (v10.11, raw fetch), `itinerary-corpus-extraction` (v10.12, structuring chain + `itinerary_corpus` Qdrant collection) — see §14 changelog entries v10.9–v10.12 for full detail on each.
