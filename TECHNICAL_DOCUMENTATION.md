# WanderPlanner — Technical Documentation

**Version:** 10.3 (Accounts, Auth Gate, Password Reset, Analytics)
**Last Updated:** July 7, 2026  
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
14. [Recent Changes (v10.3, v10.2, v10.1, v10.0, v9.0, v7.0, v6.0 & v5.0)](#14-recent-changes-v103-v102-v101-v100-v90-v70-v60--v50)

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

4. AUGMENTATION (itinerary_chain.py)
   context_text = summarise_context(context_docs, max_chars=2400)
   prompt = SYSTEM_PROMPT.format(
       context=context_text,          # ← real traveller data
       trip_config=trip_config_json
   )
   → Gemini generates itinerary grounded in real traveller data

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

## 14. Recent Changes (v10.9, v10.8, v10.7, v10.6, v10.5, v10.4, v10.3, v10.2, v10.1, v10.0, v9.0, v7.0, v6.0 & v5.0)

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
