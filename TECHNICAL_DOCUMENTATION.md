# WanderPlanner — Technical Documentation

**Version:** 10.45.0 (Voice mode had never spoken a single word in production, and it was the last feature in the product with zero tests. Two independent bugs each sufficed: `rec.onresult` captured the render *before* `setVoiceActive(true)`, so `if (voiceActive) speak(reply)` read a stale `false` on every voice turn; and one flag stood for both "the user wants a spoken conversation" and "the mic is open", so `onend` cleared the mode seconds before the reply arrived. Confirmed by reconstructing the old implementation and running it, rather than by reading. Text-to-speech also **stripped Devanagari entirely** — the allowlist used `\w`, which in JavaScript is always ASCII regardless of the `u` flag, so `clean` emptied and the next line's `if (!clean) return` produced silence; `₹` had been whitelisted, so India was in mind, just the currency and not the script. That is the **fifth** bug in this codebase's character-rule family. The new allowlist keeps `\p{M}`, because Devanagari vowel signs are combining marks and dropping them turns `खाना` into `खन` — a real word meaning something else — and keeps the danda `।`, the Hindi full stop. Three smaller defects fixed: the mic button was dead on Firefox with no feedback at all, all six recognition error codes collapsed into one silent handler so denied permission looked like a pause, and `getVoices()` was read before Chrome populates it so every cold session's first utterance used the platform default voice. **New:** an English / हिंदी toggle drives recognition language, utterance language and voice selection together — the Web Speech API has no auto-detect, so this has to be an explicit choice — and `WIZARD_SYSTEM_PROMPT` section 3a makes Anya reply in the user's language while `chips` and `config_patch` stay English, because chips are classified by English keyword match and a destination is a database key that would fork "गोवा" from "Goa". 🔴 **Anya was also speaking in a *male* voice** — the persona is a woman, the preference matched `/female/` in a voice name, and no platform puts it there; measured on the real device, `pickVoice(voices, 'en-IN')` returned Microsoft Ravi with Heera sitting beside him in the same array. **The Web Speech API exposes no gender field** — Windows records `Attributes\Gender` per voice and the browser discards it — so curated per-platform name lists are the only lever, with unrecognised names scoring neutral and still used, because not knowing a voice costs the wrong gender while refusing it costs silence. The missing-voice notice now fires at language selection rather than on Anya's first reply. Voice moved out of the 959-line `LLMWizard.tsx` into `lib/voice.ts` and `hooks/useVoice.ts`. Mobile — the bulk of the users and the least verifiable from a dev box — is instrumented rather than assumed: **Android defeats name matching entirely** (Google ships `"Google हिन्दी"`, no personal name, no gender token, so selection falls through to the platform's own order and a female Hindi default is Google landing right rather than this code doing so), **iOS Safari only permits `speak()` inside a user gesture** while Anya speaks after an awaited API call — so `useVoice` primes with a zero-volume utterance inside the toggle handler, defensively and unverified on a real device — and a new `noindex` diagnostic at `app/dev/voice` reports every voice a device exposes with its `voiceURI` and guessed gender, shows what `pickVoice` chooses and why, and speaks after a delay with no gesture on the stack, so the curated lists get corrected from real device data instead of extended by guessing. 122 frontend tests (was 44), 844 backend (was 830). Residuals stated rather than hidden: the dev machine has no `hi-IN` voice installed at all, so Hindi speech needs a Windows language pack even though Hindi recognition works; and English-in-`config_patch` is a prompt-level guarantee, not an enforced one. Previous: 10.44.0 — Derived name cores are now tested for being ordinary words instead of merely long — and the bug was an order of magnitude bigger than reported. It was filed as a demonym issue: `name_variants("Egyptian Museum")` peels the structural word and emits the bare token `egyptian`, which matched "egyptian food", giving Cairo's Egyptian Museum 30 mentions of which 29 were wrong. The same peel does it to **any** POI whose name starts with a common word or with its own city — measured on the live corpus, **Singapore Zoo had 100 mentions and now has 2, Edinburgh Castle 84 → 2, and Melbourne Museum / Melbourne Park / Melbourne City Synagogue were each absorbing the whole of Melbourne's comment volume at 59-61**. The threshold could not be raised out of it: `egyptian` is exactly 8 characters and so is `immanuel`, the genuine recovery it would cost. Length was standing in for the real question — *is this token an ordinary English word or is it specific to this place?* — which is now asked directly against a word list generated from the embedding model's own WordPiece vocabulary, committed as data so the runtime path never loads a model. A second guard in `services/gems.py` drops a variant equal to the destination's own name, which the word list cannot catch for destinations absent from it (Queenstown, Hoi An, Abu Dhabi). Across all 168 destinations: matched POIs **530 → 472**, crowd favourites **87 → 50**, gems 172 → 166, destinations returning a gem 90 → 88. Every one of those falls is a mis-attribution removed, verified POI by POI. Also corrects the TODO's framing: `poi_pinning.py` imports only `normalize_name`, so this guard has exactly one production consumer, and the "needs calibration across both consumers" caution did not apply. Previous: 10.43.0 — Input validation — the "monkey testing" pass. Nothing a user typed was bounded: `DestinationInput.city` was a bare `str`, so an empty string, `🎉🎉🎉`, `A` × 10,000, NUL bytes, zero-width spaces and an RTL override were all accepted and forwarded to the Gemini prompt, Nominatim and Overpass. New `core/validation.py` gives every user-typed field a constrained type that **rejects rather than truncates** — a silently trimmed value produces a plausible-but-wrong itinerary, the same failure shape as v10.40.0's complete-but-wrong POI pool. Four real defects surfaced that the probe had not listed: `TripConfig.dates` was unbounded and `_mock_itinerary` builds one dict per day, so `end: "2999-01-01"` was ~355,000 iterations from a single request body; unparseable dates were swallowed by a bare `except` and replaced with a hard-coded default, silently planning a different month than the user asked for; `hops` had claimed "max 5" in a comment for months without enforcing it, and each hop is its own cold-start Overpass + Wikivoyage + embedding run; and `_tips_cache` is a process-lifetime dict keyed on the raw destination string. ZWJ/ZWNJ are deliberately preserved through normalisation while every other format character is stripped — they are load-bearing in Devanagari conjuncts, and this is the **fourth** bug in this codebase's character-rule family. Deliberately *not* prompt-injection work: `core/prompt_guard.py` already covers that and was not touched. 84 new tests; suite **806 passed / 6 skipped**. Previous: 10.42.0 — First full-corpus hidden-gem audit — all **168 destinations**, measured against the live cluster with a diagnostic replica cross-checked against the shipped function on every one. v10.39.0's pool problem is fixed (Delhi now matches Chandni Chowk, Red Fort, Jama Masjid, India Gate), and the bottleneck had moved to the **sentiment floor** — which was rejecting *neutral*, not negative: Laplace smoothing puts a mention with no lexicon word in range at exactly 0.5, just under the 0.55 floor, and **75% of rejections scored exactly that**. The lexicon fired on only 29% of 1,274 real mention windows. Expanded by measuring each candidate word against the corpus — and the result inverts intuition, because YouTube enthusiasm is mostly aimed at the *video*: `great`, `nice`, `awesome`, `helpful` and `wonderful` are all creator-directed (1.7-4.6x enrichment) and are **deliberately excluded**, while `clean`, `delicious`, `historic`, `must` and `friendly` are place-directed. Also fixed cross-POI mention mis-attribution (Cairo's *Grand* Egyptian Museum was crediting the Egyptian Museum, and Seoul's Lotte World Tower the reverse) and collapsed 24 identically-named duplicate POIs. Destinations returning a gem **44% → 54%**, total gems **127 → 172**, while total matched POIs *fell* 541 → 530 as double-counts were removed. Previous: 10.41.1 — The prominence re-ingestion data run (v10.40.0's code) is now complete: **0 of 169 destinations pending**, verified on the real Qdrant Cloud cluster. Closing the last 9 surfaced a real bug: `ingest_osm_pois` returned `0` — instead of falling back to the existing stored count, like the guards immediately below it already do — when *every* Overpass mirror failed on *both* passes and the fetch came back fully empty, not just non-prominent. `scripts/reingest_prominence_ranking.py`'s state loader requires a truthy `osm_count` before its accept-after-3-attempts rule can fire, so a destination stuck on this path would retry forever; Medellin hit it three runs in a row before the fix. Also dropped the dead `overpass.openstreetmap.fr` mirror (403s on every request, a guaranteed-wasted rotation slot) and confirmed the Resend email pipeline end-to-end with a real password-reset request against production. Previous: 10.41.0 — YouTube **narration** — transcripts + video descriptions — is a new price-grounding source, discovered for free from video IDs the comment backfill already stored, so it spends nothing against the 100/day `search.list` cap. Live-measured on Jaipur: comments carry **0** money-shaped chunks, narration carries **24**. Two real bugs fell out: transcripts were requested English-only, discarding the Hindi-only track most Indian vlogs actually have; and `\b` **silently fails on Devanagari** words ending in a matra, so `खाना`/`थाली` never matched while `होटल` did — 0 of 24 price-bearing Hindi chunks matched any food or stay keyword. Previous: 10.40.6 — the bare-substring keyword bug was in FIVE modules, not one — `"pub"` inside **"Public Garden"** was deleting kid-friendly places from family itineraries, and `"uk"` inside **"Sukhothai"** was pricing a moderate destination as premium; all three now share `core/keyword_match.py`. Previous: 10.40.4 — price grounding now matches the amount, not the blob — per-amount context scoping, plus a pre-existing bare-substring bug where FOOD's "eat" matched "great"; stay grounding accepts a single mention. Measured finding: a complete corpus is not a dense one — food grounding is corpus-limited, so the `_FOOD_MEALS_PER_DAY` calibration stays deferred, now with evidence. Previous: 10.40.3 — YouTube quota discipline: a 429/403 is now terminal rather than retried 3x against a 100/day cap, and all 12 standalone scripts use the app's `RedactionFilter` instead of bare `basicConfig` — which also closed a path where the API key could reach a JSONL state *file*, where no logging filter runs. Corrects a v10.40.1 claim: the cold-start gate does not over-subscribe the cap on its own. Previous: 10.40.2 — YouTube comment corpus complete at 170/170 destinations — 25,347 points verified on the cluster; and `mypy .` runs for the first time, going from an abort-before-checking to `Success: no issues found in 166 source files`, which surfaced three real bugs: a cancelled ingestion reading as a success, and two in the comparison path)
**Last Updated:** July 28, 2026  
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
8A. [Evaluation & Quality Assurance](#8a-evaluation--quality-assurance)
8B. [Single-Agent vs. Multi-Agent Architecture](#8b-single-agent-vs-multi-agent-architecture--why-single-agent-today)
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
| **Qdrant** | 1.x | Vector DB — managed **Qdrant Cloud** since 2026-07-15 (persistent, shared across processes). `:memory:` is a local-dev-only fallback, not production |
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
│   ├── page.tsx            — Landing page (LandingHero + wizard overlay) only
│   ├── itinerary/page.tsx  — Generated trip: ThreeColumnLayout + Anya + overlays.
│   │                         Redirects to / when there is no itinerary (waits
│   │                         on sessionStorage rehydration first)
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
│   │   ├── BookingExpensesPanel.tsx — "Booking & Expenses": expenses, expert,
│   │   │                             booking links, saved bookings, currency
│   │   │                             (was Column1Metrics until v10.56.0)
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

### Page Layout — two routes, not one (v10.55.0)

These used to be a single `/` page switching on `days.length > 0`, which is why
the URL never changed and why logout could not navigate away from a trip.

```
/  (app/page.tsx)
<div h-screen flex flex-col>
  ├── [Content area] — blurred/dimmed when wizard open
  │    └── <LandingHero />
  └── <LLMWizard />             when wizardOpen (fixed overlay, LLM-powered)

/itinerary  (app/itinerary/page.tsx)
<div h-screen flex flex-col>
  ├── [Content area] — blurred/dimmed when wizard open
  │    └── <main><ThreeColumnLayout /></main>
  │
  ├── <FloatingAnyaButton />    when wizard closed
  ├── <ChatPanel />             hidden until opened
  └── <LLMWizard />             when wizardOpen
```

**Inside `ThreeColumnLayout` (v10.56.0)** — mobile tabs and desktop columns
render the *same* three groups in the same order:

```
1. Itinerary          <TripSummaryHeader />   metrics + Edit Trip + PDF
                      <ItineraryTimeline />   day-by-day

2. Booking & Expenses <BookingExpensesPanel />
                        <ExpenseBreakupCard />   collapsed by default
                        <AgentHandoffCard />     pitch + CTA → AgentQuoteModal
                        <BookingLinksSection />
                        <BookingHub />
                        <CurrencyWidget />

3. Maps & Tips        <Column3Sidebar />
                        <MapWrapper /> · <BestTimeWidget /> · tips & community
```

Navigation into `/itinerary` happens on generation success
(`LLMWizard.tsx`); the route redirects to `/` when there is no itinerary, but
only **after** `useItineraryStore.persist.hasHydrated()` — `days` is `[]` on
the first client render, so an eager redirect would bounce every refresh.

---

## 5. State Management (Zustand)

Ten stores, all in `apps/web/store/`. Three are persisted: `itineraryStore` and
`tripConfigStore` to **sessionStorage** (tab-scoped, so `/itinerary` survives a
refresh without a trip outliving the tab — both cleared by
`authStore.logout()`), and `bookingStore` to **localStorage** (saved bookings
are meant to last across sessions):

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
│   └── scheduler.py          — APScheduler jobs: OSM POI refresh (weekly), YouTube comment refresh (14d); reddit refresh retired 2026-07-26
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
│   ├── reddit.py             — ⛔ retired 2026-07-26 (source withdrawn); still defines KNOWN_DESTINATIONS, read elsewhere
│   ├── wikivoyage.py         — Wikivoyage HTML scraper → Qdrant ingestion
│   └── osm.py                 — ⭐ NEW (v9.0): Overpass API POI scraper → Qdrant 'osm_pois' ingestion
├── eval/                      — ⭐ NEW (v9.0)
│   ├── golden_dataset.json    — curated corpus + labeled queries for retrieval eval
│   └── run_rag_eval.py        — Precision@k/Recall@k/MRR/nDCG@k against retrieve_context() (issue #50)
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
Returns Gemini-generated tips + community highlights. Cached 1 hour. (The `reddit_highlights` response field keeps its name for API compatibility, but the underlying collection is frozen as of 2026-07-26 — it serves previously-ingested points only.)

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

WanderPlanner uses RAG to inject real traveller knowledge from Wikivoyage, YouTube traveller comments, and OpenStreetMap into Gemini's itinerary generation prompt. (Reddit was a source until 2026-07-26; its collection is still read but no longer written — see §14.) As of v9.0, retrieval is hybrid (BM25 + semantic), augmented with HyDE, optionally reranked with a cross-encoder for the primary generation path, and backed by a 3-tier RAG-powered fallback chain for LLM outages.

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
   │ scrapers/reddit.py  ⛔ RETIRED 2026-07-26              │
   │   Source withdrawn: Reddit 403s unauthenticated reads │
   │   and its OAuth API review never issued credentials.  │
   │   Code and the 'reddit' collection remain (read-only, │
   │   degrades to empty); nothing writes to it any more.  │
   │   Historic behaviour, for reference:                  │
   │   → Reddit JSON API (r/travel, r/solotravel, ...)    │
   │   → _extract_destination(): regex against KNOWN_DESTS │
   │   → _chunk_reddit_post(): paragraph-level chunks     │
   │   → upsert into Qdrant 'reddit' collection            │
   └──────────────────────────────────────────────────────┘
   ┌──────────────────────────────────────────────────────┐
   │ scrapers/youtube_comments.py  (replacement source)   │
   │   → search.list video discovery (quota-budgeted)     │
   │   → commentThreads.list comment scraping             │
   │   → upsert into Qdrant 'youtube_comments' collection │
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
- `apps/api/eval/golden_dataset.json` — curated corpus + 20 labeled queries with expected-relevant chunk IDs (9 now carry `personas`/`purpose`/`crowd_preference` overrides — see below)
- `apps/api/eval/run_rag_eval.py` — computes Precision@k, Recall@k, MRR, nDCG@k against the **real** `retrieve_context()` production path (issue #50, resolved), reranking on — exercises the full HyDE + hybrid-search + cross-encoder pipeline end-to-end, not the isolated `semantic_search()` pass it used before
- **Current results** (measured through the real path): Recall@10 = 0.95, MRR ≈ 0.46, nDCG@10 ≈ 0.58 — a material, **honest** drop from the old `semantic_search()`-only numbers (Recall@10 = 1.00, MRR ≈ 0.85–0.94, nDCG@10 ≈ 0.89–0.96), not a regression: production runs three broad query variants (config, vibe, practical-logistics) merged via Reciprocal Rank Fusion, which necessarily dilutes rank for narrow single-topic queries versus the old harness's one sharp query straight into `semantic_search()`. This is what real itinerary generation actually retrieves — the eval now measures reality instead of a flattering proxy. See `docs/eval-set.md` §4U for full methodology, the metric definitions, and how to run.

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
{context}   ← RAG-retrieved chunks from Qdrant (Wikivoyage + YouTube comments)

TRIP CONFIGURATION:
{trip_config}
```

---

## 8A. Evaluation & Quality Assurance

All AI surfaces above (wizard chat, itinerary generation, refinement) are
non-deterministic and can't be fully covered by traditional pass/fail unit
tests. `apps/api/eval/` holds a set of live-LLM eval harnesses, one per
surface, all following the same **dataset → inference → grading → failure
analysis → optimize** loop ("Quality Flywheel" — see `docs/eval-set.md` §7
for the full methodology and process-discipline rules, `docs/system-design.md`
§15A for architecture detail, `docs/PRD.md` §10 for the product-facing
"types of evals" breakdown).

| Harness | Surface | Grading |
|---|---|---|
| `run_wizard_eval.py` | Anya wizard multi-turn chat | Deterministic invariant checks (`wizard_checks.py`) replaying scripted conversations — e.g. catches chips shown for the wrong field after a topic-shifting reply |
| `run_rag_eval.py` | RAG retrieval (§8 above) | IR metrics (precision/recall/MRR) against a labeled golden query→chunk dataset |
| `run_refinement_eval.py` | Pinned-POI refinement (§8/§12) | Recall/precision/inclusion/stability + honesty, reusing the production fuzzy name matcher |
| `run_red_team_eval.py` | Injection/safety surfaces (`core/prompt_guard.py`) | Canary/keyword/cost-abuse checks per adversarial case |
| `run_model_comparison.py` | Itinerary generation model selection | Deterministic accuracy/hallucination + **LLM-as-judge** (`judge_metrics.py`: tone/personalization/coherence, scored by a model fixed independently of whichever model is under test) + cost/latency |
| `run_budget_comparison.py` (⭐ NEW 2026-07-21) | Budget estimation: WanderPlanner's own deterministic estimator vs. asking a general-purpose chatbot directly | 5 real-anchor-documented cases (`budget_comparison_dataset.json`); scores anchor adherence, no-answer rate, false-positive info-already-given stalls, breakdown rate, hedge-language use, and run-to-run variance (the estimator is exactly 0.0 by construction; LLMs asked 3x are not) — see `docs/eval-set.md` §10 |

**Eval-only LLM providers** (`eval/llm_providers.py`, not wired into
production inference): OpenAI GPT-4o-mini, Anthropic Claude 3.5 Haiku,
Google Gemini 2.5 Flash, and (⭐ NEW 2026-07-21) Moonshot/Kimi
(`kimi-k2-0711-preview`), added specifically for `run_budget_comparison.py`
so the eval covers the same model spread a real user might ask directly.

**Supporting tools** (⭐ NEW 2026-07-18): `compare_results.py` diffs two
timestamped result files metric-by-metric to flag regressions between a
baseline and a candidate run; `analyze_results.py` clusters failing cases
by category/check/reason instead of leaving them in a flat list;
`eval_config.json` (loaded via `config_loader.py`) externalizes which
wizard checks run, the judge model and enabled/disabled toggle, default
`--runs`/`--scale`, and failure-analysis thresholds, so these can be tuned
without editing runner code. Every harness run now writes a timestamped
`out/<harness>_results_<ts>.json`/`.md` pair (plus a fixed-name "latest"
alias) instead of overwriting a single fixed filename each time.

---

## 8B. Single-Agent vs. Multi-Agent Architecture — Why Single-Agent Today

A recurring demo-day question: is this a multi-agent system? **No — it's a
single-agent, multi-chain architecture.** One LLM (Gemini) is invoked through
8 independently-prompted chains (§8 table above), each with its own system
prompt and temperature, dispatched by deterministic FastAPI routers based on
which endpoint the frontend calls — there is no autonomous agent framework,
no agent-to-agent negotiation, and no LLM-driven handoff between chains.
Orchestration is plain backend code, not an orchestrator agent.

**Why this is the right call at current scope, not just an accident of
history:**
- **The product moat doesn't require it.** Per `docs/GTM_STRATEGY.md`, the
  moat is the verified India corpus, measurable personalization fidelity,
  and offline-agent distribution — none of that is unlocked by inter-agent
  orchestration.
- **Latency budget is already tight.** The PRD's 15–20s generation window
  leaves little room for multi-hop planner→critic→executor loops, which
  multiply LLM round-trips.
- **Cost discipline.** Solo-founder, pre-revenue, pay-per-token — every
  extra agent hop is a directly billed cost for marginal benefit already
  captured cheaply via prompt/temperature specialization on one model.
- **Operability.** Multi-agent systems compound failure modes and are
  harder to eval; the current eval suite (§8A) already catches real bugs
  (e.g. RAG silently returning nothing in prod for months) in the *simple*
  architecture — that diagnostic clarity would be harder to preserve with
  multiple interacting agents.
- **Determinism where it matters.** Safety filters (`chains/safety.py`),
  persona injection, and the 3-tier fallback chain are deterministic Python,
  not agent decisions — more testable and debuggable than delegating them
  to an LLM.

**When multi-agent would start to earn its keep (explicitly not now):**
autonomous multi-step booking/negotiation across live third-party APIs with
re-planning; per-market behavioral specialization at real scale (not just
prompt swaps); a "verifier" agent role — though this is already handled more
cheaply today via deterministic OSM/wiki verification code rather than a
second LLM call. See `docs/system-design.md` §1A and
`docs/scaling-tech-challenges.md` §9 for the fuller architecture rationale
and the concrete trigger conditions that would justify revisiting this.

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

Layout (desktop `lg+`) — regrouped in ⭐ v10.56.0 so each column matches its
mobile tab exactly:
- **Left (25%)**: `BookingExpensesPanel` → expenses (collapsed), local expert, booking links, `BookingHub`, currency (falls back to `destination_country` when a trip resolves to a country rather than one fixed city — ⭐ v10.2)
- **Center (flex-1)**: top-bar with destination, `ThemeToggle` (⭐ v10.2 — previously only present on the shared `/t/[slug]` page), and `ShareButton`, then `TripSummaryHeader` (metrics, Edit Trip, PDF — shows "City +N" for multi-hop trips) above `ItineraryTimeline`, or `ComparisonPanel`
- **Right (25%)**: map + "⤢ Full screen" toggle, then `Column3Sidebar` → best time + travel tips & community (same `destination_country` fallback — ⭐ v10.2)

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

## 14. Recent Changes (v10.57, v10.56, v10.55, v10.54, v10.53, v10.52, v10.51, v10.50, v10.49, v10.48, v10.47, v10.46, v10.45, v10.44, v10.43, v10.42, v10.41, v10.40, v10.39, v10.38, v10.37, v10.36, v10.35, v10.34, v10.33, v10.32, v10.31, v10.30, v10.29, v10.28, v10.27, v10.26, v10.25, v10.24, v10.23, v10.22, v10.21, v10.20, v10.19, v10.18, v10.17, v10.16, v10.15, v10.14, v10.13, v10.12, v10.11, v10.10, v10.9, v10.8, v10.7, v10.6, v10.5, v10.4, v10.3, v10.2, v10.1, v10.0, v9.0, v7.0, v6.0 & v5.0)

### v10.57.0 Changes (August 2026) — the auth card puts both routes at the top

Frontend **168 passed** (+15), `tsc --noEmit` clean. From a live look at
`/signup`: the card read heavy, and a returning user's way out of it —
"Already have an account? Log in" — was the *last* thing on the page, below the
card, after every field, in `--_muted-fg`.

**New `components/common/AuthSwitch.tsx`** — a segmented Sign up / Log in
control rendered inside the card above the heading. `AuthLayout` gained an
optional `switcher` slot for it; `/login` mirrors `/signup`, and
`/forgot-password` / `/reset-password` pass none, so they are unchanged.

| | Before | After |
|---|---|---|
| Log-in affordance | below the card, after the form, `--_muted-fg` | tab 1 of 2, above the heading |
| Logo top → last element (696×825) | 618px | **580px** |
| Card | 500px | 513px |

- ⚠️ **Active state is carried by the pill, not by colour — this is a WCAG
  constraint, not a preference.** The obvious styling (active `--_fg`,
  inactive `--_muted-fg`) puts the inactive label at **~4.05:1** on the
  light-mode track — `#64748B` on `#F0F9FF` — and 14px semibold does **not**
  qualify as WCAG large text (that needs 18.66px bold), so it fails AA. Since
  the entire point of the change is that the inactive route be easy to see,
  colour is the wrong channel for active state here. Both labels render at
  full `--_fg`; `bg-[var(--_card-elevated)]` + a `--_border` ring marks the
  current route. That choice also fixes dark mode, where the `--_card` pill
  first tried is nearly invisible on a `--_bg` track — `#0D2236` on `#040D14`
  is not.
- ⚠️ **`returnTo` must survive the tab hop, and its failure mode is silent.**
  `LLMWizard.tsx` (2 call sites) and `ChatPanel.tsx` push
  `/signup?returnTo=…`; `app/account/page.tsx` and `app/admin/page.tsx` link to
  `/login?returnTo=…`. A switcher that dropped the param would return the user
  to `/` after authenticating instead of to the gate that stopped them — no
  error, no broken link, just the wrong page. Both hrefs are built from the
  page's own `useSearchParams()` value and pinned by test at all four origins.
- Tabs are `min-h-11` (44px), matching the touch-target standard already used
  by the password-reveal button and the consent checkbox on these forms.
- `aria-current="page"` on the active tab; the wrapper is a `<nav>` labelled
  "Sign up or log in". Deliberately **not** `role="tablist"` — these are route
  links, and tab semantics would promise a `tabpanel` that does not exist.
- **Compaction** (the smaller half; the 70px control eats most of it): card
  padding `sm:p-8` → `p-5`, form rows `space-y-4` → `space-y-3`, label gaps
  `mb-1.5` → `mb-1`, logo margin `sm:mb-8` → `sm:mb-6`, children `sm:mt-6` →
  `mt-4`, and the now-duplicated footer removed from both pages. No page
  scroll at 696×825 or 375×812.

**Tests** — `__tests__/components/AuthSwitch.test.tsx` (both routes present,
`aria-current` on the live route only, `returnTo` encoded into both hrefs) and
`__tests__/components/AuthPages.test.tsx`, parameterised over both pages: the
switcher precedes the `<form>` in document order (the prominence claim, pinned
so a later refactor cannot quietly demote it), no duplicated footer link, and
`returnTo` preserved across the switch for each of the four real deep-link
origins plus the `/` default.

⚠️ **Not verified by screenshot or on a real device.** The browser pane would
not composite frames during this session, so every measurement above is DOM
geometry read via `getBoundingClientRect()` and computed style — the before
numbers came from `git stash`-ing the change and re-measuring the same page.
Contrast ratios are arithmetic on token values, not sampled pixels.

### v10.56.0 Changes (August 2026) — dashboard regrouped around user intent, and the expert card decluttered

Frontend **129 passed**, `tsc --noEmit` clean, production build clean. From a
live mobile review: the three panels had drifted into holding whatever was
added last, so the mobile tab names no longer described their contents.

**The three sections are now grouped by what the user is trying to do**, and
desktop mirrors mobile exactly — the same three groups in the same order, so
the two layouts stay one information architecture instead of two.

| Tab | Before | Now |
|---|---|---|
| **Itinerary** | day-by-day only | **trip metrics + Edit Trip + Download PDF**, then the day-by-day |
| **Booking & Expenses** (was "Overview") | trip metrics, actions, expenses, expert card | **estimated expenses (collapsed)**, local expert, book this trip, my bookings, currency |
| **Maps & Tips** (was "Map & Tips") | map, best time, booking links, my bookings, tips | **map, best time, travel tips & community** |

- New `components/itinerary/TripSummaryHeader.tsx` — metrics + the two
  whole-trip actions, extracted from the old `Column1Metrics`. These describe
  the itinerary, and on mobile they were parked behind a tab whose own content
  is consulted far less often.
- `Column1Metrics.tsx` → **`components/dashboard/BookingExpensesPanel.tsx`**.
  The old name had become actively misleading — a "metrics" panel with no
  metrics left in it. Ordered along the decision sequence: what will it cost →
  who can help → where do I book → what have I already booked.
- `Column3Sidebar.tsx` loses `BookingLinksSection` and `BookingHub`. Those are
  purchase actions, not orientation material.
- `MobileTab` type: `'overview'` → `'bookings'`.
- ⚠️ **`ExpenseBreakupCard` was already collapsed by default** (`useState(false)`)
  and needed no change — recorded so nobody "fixes" it again.

**Local expert card: the form moved into a modal.** On a phone the card
rendered an email field, a 100-word textarea and a live word counter inline,
pushing the actual CTA most of a screen down and making a single offer look
like a form to fill in. The card now carries the pitch, the 24-hour proof
point and one button; new `AgentQuoteModal.tsx` collects email + notes after
the user has opted in. All submit logic (PDF attachment, itinerary HTML, lead
creation, feedback prompt) is unchanged.

The modal meets the v10.48.0 accessibility bar: labelled dialog, Escape to
close, Tab trapped inside, background scroll locked, focus restored to the
trigger. Two details worth keeping:

- 🔴 **`onClose` must not be an effect dependency.** Callers pass an inline
  arrow, so depending on it re-runs the whole effect on every parent render —
  tearing down and re-adding the keydown listener, re-applying the scroll
  lock, and re-capturing the focus-restore target from whatever is focused
  *then* (a field inside the dialog) rather than the element that opened it.
  Held in a ref; the effect depends on `open` alone.
- **Focus goes to the first form field, not the first focusable.** The close
  button precedes the fields in DOM order, so a plain focusable query lands
  the user on "dismiss" — the one control they did not open the dialog to use.

**Verified in the browser at a 375×812 mobile viewport**, not asserted: the tab
labels read Itinerary / Booking & Expenses / Maps & Tips; the itinerary tab
opens with TRIP METRICS → Edit Trip → Download PDF → Day 1; the booking tab
renders expenses (collapsed) → expert → book this trip → my bookings in that
DOM order; the maps tab no longer contains either booking section; the modal
opens labelled with focus on the email field, closes on Escape, restores focus
to the trigger and unlocks scrolling.

### v10.55.0 Changes (August 2026) — three live-reported auth/routing bugs, one shared root cause

Backend **1091 passed / 6 skipped** (+2), ruff + mypy clean (205 files); frontend
**129 passed** (+3), `tsc --noEmit` clean. All three reports traced back to the
itinerary having no route of its own.

**1. 🔴 The itinerary had no URL.** `app/page.tsx` rendered either `LandingHero`
or the full `ThreeColumnLayout` off `days.length > 0`, both at `/`. So the
address bar never changed, back/forward did nothing meaningful, and a trip
could not be linked to. Now `/` is the landing page only and the trip lives at
**`/itinerary`**, with `LLMWizard` navigating there on generation success.

**2. 🔴 Logout appeared to do nothing on the itinerary page — and the cause was
the missing route.** `UserMenu.handleLogout()` ended with `router.push('/')`,
which is a **no-op when you are already on `/`**. `authStore.logout()` cleared
only `user`, so `days` stayed populated and the dashboard kept rendering: the
user pressed Log out and watched their itinerary sit there. Fixed on both
sides — logout now clears the itinerary, trip-config and chat stores (plus
their persisted copies) and `router.replace('/')` leaves no dead history entry.
`logout()` also **swallows a failed API call** rather than propagating it: the
old code awaited `apiLogout()` with no catch, so a rate-limited or offline
logout aborted before the local session was cleared and silently did nothing.
`app/account/page.tsx` had always guarded this with `.catch(() => {})`; the
menu had not.

**3. 🔴 Logging out left you logged in — the deletion header was ignored.**
`_clear_session_cookies()` called `response.delete_cookie(name, domain, path)`
and inherited Starlette's defaults, emitting:

```
wp_access_token=""; Max-Age=0; Path=/; SameSite=lax
```

while `_issue_session()` set the cookie with `Secure; SameSite=none; HttpOnly`.
A `Set-Cookie` is only honoured in a **cross-site** response when it carries
`SameSite=None; Secure` — and this deployment *is* cross-site, which is exactly
why `COOKIE_SAMESITE=none` is required in production (the v10.26 session-drop
fix). The browser therefore ignored the deletion, kept both cookies, and
`/api/auth/me` went on answering 200 until the 15-minute access token expired.
The DB-side refresh-token revocation had always worked, which is why this never
showed up in a test: **the cookie attributes, not the revocation, were the
bug.** Issuance and deletion now share one `_cookie_kwargs()` so they cannot
drift again, covered by a test asserting the deletion carries `Secure`,
`SameSite=none` and `HttpOnly`.

**Persistence, and why sessionStorage.** A route with no persisted state would
bounce to the landing page on every refresh — worse than no route at all. The
itinerary and trip-config stores now persist, deliberately to **sessionStorage,
not localStorage**: it is scoped to the one tab and dies with it, so a
generated trip does not outlive the browsing session on a shared machine.
Logout clears it explicitly on top of that. `status`/`progress`/`error` are
excluded via `partialize` — they describe an in-flight generation and would
restore as a permanently "loading" screen.

⚠️ **The route guard waits for `persist.hasHydrated()` before redirecting.** On
the first client render `days` is always `[]`, so an eager redirect would send
every refresh back to the landing page — the exact failure the route was added
to prevent.

**Verified in the browser, not just asserted:** `/dev` → itinerary lands on
`/itinerary` with the dashboard rendered and both stores in sessionStorage; a
reload restores Tokyo / ₹1,50,000 / 3 days at the same URL; clearing storage
and hitting `/itinerary` directly redirects to `/`. No hydration errors from
the persist middleware (the pre-existing `<script>` console warnings come from
`app/layout.tsx`'s theme + JSON-LD tags and are untouched here).

### v10.54.1 Changes (August 2026) — CI restored to green (1 ruff + 8 mypy errors)

`ruff check .` and `mypy .` were both failing at `9e876ba`, so CI was red on
`main`. Confirmed pre-existing against a pristine worktree at that commit
before changing anything — none of it came from v10.54.0. Full suite
**1089 passed / 6 skipped** (`pytest tests/`), ruff + mypy clean (204 files).

- **`models/itinerary_feedback.py`** — UP037, quoted return annotation that
  `from __future__ import annotations` already makes unnecessary.
- **`routers/itinerary_feedback.py`** — `scope`/`sentiment` come back from
  plain `String` columns but the response model declares `Literal`s. Cast at
  the boundary with the reason stated: every write goes through the
  create/update request models, which validate against exactly those sets.
  Same shape as `routers/auth.py`'s existing cast of `cookie_samesite`.
- **`core/email.py`** — the `payload` literal inferred as
  `dict[str, Sequence[str]]` (a bare `str` satisfies `Sequence[str]`), so
  attaching `list[dict[str, str]]` did not fit. Annotated `dict[str, object]`.
- **`routers/admin.py`** — ⚠️ **not the latent `AttributeError` it looked
  like**: the query filters `responded_at.is_not(None)`, so the value is never
  None at runtime; the column is merely nullable. Narrowed with a `continue`
  rather than an assert, since a bookkeeping metric should not 500 on an
  unexpected row. Separately, the `series` dict was typed `int` while the
  `agent_lead_response_avg_hours` entry is a rounded average — widened to
  `float`.
- **`routers/share.py` / `routers/travel_tips.py`** — `Cache.get_json()`
  returns `object | None` **by design** (it round-trips arbitrary JSON), so
  both call sites narrow with `isinstance` instead of the Protocol being
  widened to `Any`, which would have silenced the error everywhere and lost
  the safety. Both now also skip a malformed or legacy cache entry rather than
  raising on it.
- **`tests/unit/test_input_validation.py`** — `ChatRequest(messages=[{...}])`
  passes dicts where `list[ChatMessage]` is declared. Switched to
  `ChatRequest.model_validate({...})`, which keeps the test validating a raw
  client payload through `ChatRequest` — constructing `ChatMessage` objects
  directly would have moved the assertion to a different boundary.

### v10.54.0 Changes (August 2026) — first `visa_info` data run (#59) + a disambiguation-title fallback found by it

Suite **1032 passed / 6 skipped** (`pytest tests/unit`), up 5 from v10.53.0's 1027; the
new scraper/script files are ruff + mypy clean.

**The data run.** `visa_info` shipped fully wired in v10.52.0 but had never been
ingested, so the collection was empty. Because `services/visa.py::retrieve_visa_note()`
degrades to `""` on an empty corpus, the wizard correctly said nothing and the feature
looked *fine* — a silent no-op rather than a visible failure, which is exactly why it
needed an explicit run rather than waiting to be noticed. Waiting for the scheduler was
not an option either: `visa_info_refresh` uses an `IntervalTrigger`, and APScheduler
schedules the **first** fire at now+interval, so a fresh deploy ingests nothing for 30
days.

New `apps/api/scripts/ingest_visa_info_full.py` — resumable (one JSON line per country),
`--fresh` to restart, politeness-paced for Wikimedia. No quota cost: this is the free
`action=parse` API, one article per country, no key. Done-rule follows
`ingest_youtube_full.py`: **done means chunks were actually ingested**, with a 3-attempt
cap, so a transient failure stays pending instead of being recorded as an empty success.

**Result, verified against the live cluster rather than the run log: 1,291 points across
73/73 seed countries** (USA 77, Cambodia 53, India 47, Canada/UK 43). Also verified on
real stored payloads: `retrieve_visa_note()` returns attributed notes carrying
`source_url` and `""` for a country outside the seed list; **zero `[ edit ]` markers**
survived in 1,291 payloads; every point carries the full v10.50.0 unified metadata.

🔴 **The run found a real bug — 72/73 on the first pass.** "Georgia" returned zero
chunks. `/wiki/Georgia` redirects to a **disambiguation page** while the country guide
lives at `Georgia (country)` and holds 17 entry-rule chunks. The bare title answers
**200 OK**, so no status-based check could ever have seen this — the same failure shape
as `scrapers/wikivoyage.py`'s New York case (a real but structurally different article,
not a 404).

`scrape_visa_info()` now retries with the `"<Name> (country)"` suffix **only when the
bare title yielded no entry rules at all**. A suffix retry rather than a hand-pinned
title map (the `WIKIVOYAGE_TITLE_OVERRIDES` approach) because it encodes Wikivoyage's
own naming convention instead of one fact, costs nothing on the happy path, and still
returns `[]` when the variant does not exist either. **The country is stored under its
plain name** — the suffix belongs to the wiki's title, not to our key — and a test pins
that specifically, since storing `"Georgia (country)"` would have silently broken
`retrieve_visa_note("Georgia")`, which filters on an exact `destination` match.

⚠️ **The inverse case was audited, not assumed.** A zero is visible; the dangerous
version is a bare title resolving to a real but *wrong* article that still yields plenty
of chunks — which a point count structurally cannot catch, the same shape as the
2026-07-24 mis-geocoded destinations. All 73 titles were queried against MediaWiki for
redirects, `pageprops.disambiguation` and category membership: **only Georgia was
flagged**, the other 72 resolve to genuine country articles, and
`United States of America → United States` is a correct redirect. Re-run that audit if
`VISA_SEED_COUNTRIES` grows.

### v10.53.0 Changes (July 2026) — Mobile landing UX (inspiration above the fold, nav decluttered) + chat profanity gate

**Landing page mobile UX**, prompted by a live screenshot review with the
`ui-ux-pro-max` skill: the Features/"How it works" strip in `LandingHero.tsx`
pushed the Inspiration gallery below the fold on mobile, and a redundant
"Plan a trip" plane-icon nav button (a second entry point for the same hero
CTA) added clutter while the Inspiration/FAQ anchor links stayed
`hidden sm:block` — invisible on the exact viewport that most needed a
shortcut to them.
- Reordered sections so **Inspiration renders immediately after the hero
  CTA**, ahead of Features.
- **Features compressed on mobile** into a horizontally-scrollable chip row
  (smaller icons, descriptions moved to `sr-only` and restored visually from
  `sm:` up) instead of a tall stacked grid.
- **Removed the "Plan a trip" plane-icon nav button** and used the freed
  space to make **Inspiration/FAQ anchor links visible on mobile**
  (previously desktop-only).
- `tsc --noEmit` clean; no backend changes.

**Chat profanity gate.** A review of negative-testing coverage
(`core/validation.py`'s existing junk/oversized-paste/paragraph tests) found
garbage-input handling well covered but no check for profane language typed
directly into chat — `better-profanity` (already a declared dependency, used
only for scraped Reddit content in `scrapers/reddit.py`) was not wired into
any user-facing input path.
- Added an opt-in `require_no_profanity` flag to `text_validator`, enabled
  **only** on `ChatMessageText` (the field where a user addresses Anya
  directly).
- Deliberately **not** applied to `FreeFormTripText` (the "start from a
  blog/Reddit post" box) — pasted third-party content can legitimately quote
  a swear word, and rejecting it would break that feature.
- New tests: plain/mid-sentence/spaced-out profanity rejected with a 422;
  clean chat text still accepted. Full suite **1024 passed / 6 skipped**, up
  from v10.49.0's 917.

### v10.52.0 Changes (July 2026) — entry/visa corpus from free sources (#37)

Suite **976 passed / 6 skipped** (`pytest tests/`), up 18 from v10.51.0's 958; ruff clean,
mypy clean (61 files).

New `visa_info` Qdrant collection, `scrapers/visa_info.py`, `services/visa.py`, a monthly
`visa_info_refresh` scheduler job, and a gated hint in the wizard prompt.

🔴 **Keyed by COUNTRY, not city — measured, not assumed.** #37 proposed scraping the
existing destination list. Counting visa/passport/e-visa mentions inside each article's
"Get in" section on 2026-07-29:

| | | | | | | |
|---|---|---|---|---|---|---|
| India **76** | Thailand **30** | UAE **31** | France **28** | Japan **16** | Jaipur **0** | Bangkok **0** |

Scraping the ~170 city guides would have yielded almost nothing; ~70 country articles cover
all of them. Per-city keying would also have stored one country's rules 170 times, each copy
drifting as it refreshed on its own schedule.

**This is genuinely new corpus, not a duplicate of `wiki`.** `scrapers/wikivoyage.py`'s
`SECTIONS_OF_INTEREST` is `{go, stay_safe, see, do, eat, drink, sleep, understand}` matched
as substrings, and `get_in` contains none of them — so entry rules had never been ingested
for any destination.

The subsection holding the rules is **not consistently named** (India "Visa", Thailand/
France/UAE "Entry requirements", Japan none), so the scraper takes the whole `Get in` H2
including subsections and filters chunk-by-chunk on visa vocabulary through
`core/keyword_match.py` rather than hunting for a heading by name. Whole-word matching is
load-bearing: **bare-substring "visa" matches "Visakhapatnam"**, an Indian city this product
will genuinely see — the sixth instance of the v10.40.4/5/6 bug class, caught before it
shipped this time. Pinned by test.

🔴 **A defect found by reading the scraped text rather than the chunk counts.** France and
UAE came back with literal `[ edit ]` runs embedded mid-sentence — MediaWiki's per-heading
edit links, which `get_text()` pulls in whenever a section includes its subsection headings.
Counts looked perfect (20 and 15 chunks). These chunks are both embedded *and* surfaced into
the wizard prompt, so the noise would have shifted the vectors and been visible to users.
Stripped, with a regression test. **Same lesson as v10.40.1's `0 comments ingested`: the
count was never going to show it.**

**Live, read-only, through the shipped scraper:** India 47 chunks, Thailand 26, France 20,
UAE 15, Japan 13, Bhutan 13.

**Retrieval is deliberately conservative.** `services/visa.py::retrieve_visa_note()` returns
a short note *with its source URL and an explicit "confirm with the official immigration
site" line*, or `""`. It never states a determination, and any failure degrades to silence —
a traveller acting on a stale visa rule misses a flight, so the asymmetry is nothing like a
bad restaurant suggestion. The wizard prompt is instructed not to answer from its own
knowledge when nothing is on file.

⚠️ **The wizard hint is gated on the user actually asking** (`_visa_hint_for`,
whole-word matched). An unconditional lookup would put an embedding plus a Qdrant round-trip
on *every* wizard turn's critical path to serve a question that comes up in a minority of
conversations — v10.47.0's latency work is why this is a gate, not an always-on hint.

**Not done:** no ingestion run has been performed, so the collection is empty until the
scheduler's first fire or a manual run. `visa_info_retrieval_enabled` defaults on, but with
an empty collection the wizard correctly says nothing.

---

### v10.51.0 Changes (July 2026) — Wikivoyage district sub-article scraping for hub cities (#45)

Suite **958 passed / 6 skipped** (`pytest tests/`), up 7 from v10.50.0's 951; ruff clean,
mypy clean.

Big-city guides delegate their priced Budget/Mid-range/Splurge listings to per-district
sub-articles, so the parent guide alone under-reports what Wikivoyage actually documents.
`scrapers/wikivoyage.py` now discovers and ingests those sub-articles, tagged with the
**parent city** as `destination` (so everything stays retrievable under one key) plus a
`district` field for provenance. Capped by `settings.wikivoyage_max_district_subpages`
(default 8; `0` disables).

🔴 **The mechanism in the issue would have silently ingested nothing, and this is the
finding worth keeping.** Issue #45 specified detecting hub articles by parsing links out of
the guide's "Districts" section. Measured live 2026-07-29: Paris, Bangkok, Tokyo and London
render **zero** `/wiki/<City>/<District>` hrefs, and their Districts sections contain only
`Special:Map` links — Wikivoyage builds those lists through map/template markup, not plain
article links. The sub-pages exist in bulk regardless (Paris 21 non-redirect, Tokyo 29,
Bangkok 12, Delhi 6), so discovery goes through `list=allpages&apprefix=<City>/` instead.
**A link-parsing implementation would have shipped, passed unit tests written against a
hand-made fixture, and quietly done nothing in production** — the same
complete-but-wrong shape as v10.40.0's POI pool and v10.40.1's `0 comments ingested`.
`test_discovery_uses_allpages_not_link_parsing` pins the mechanism so it can't regress
back.

`apfilterredir=nonredirects` is load-bearing, not incidental: Wikivoyage aliases districts
heavily (`Paris/10th` → `Paris/10th arrondissement`; three spellings of
`Bangkok/Banglamphu`), so unfiltered enumeration would fetch, embed and store the same
district several times.

**Live end-to-end through the real `scrape_wikivoyage()` at the default cap of 8** — chunks
and price-bearing chunks, measured with `has_price_mention()`, the same way §A measured
Jaipur:

| destination | chunks | price-bearing | |
|---|---|---|---|
| Paris | 156 → **377** | 28 → **123** | ×4.4 |
| Bangkok | 143 → **680** | 17 → **67** | ×3.9 |
| Tokyo | 94 → **293** | 11 → **31** | ×2.8 |
| Delhi | 64 → **312** | 8 → **65** | **×8.1** |
| Jaipur (control) | 141 → 141 | 74 → 74 | 0 districts, unchanged |

**Delhi gains the most of any city measured**, which matters for an India-first product,
and Jaipur is the control proving non-hub destinations pay nothing — zero extra article
fetches, asserted in `test_non_hub_city_fetches_no_extra_articles`.

⚠️ **The issue's stated motivation was already stale when it was picked up.** It says these
cities produce "zero food/stay pricing data"; they no longer do — the §A `<section>` parser
fix (`9fa3106`) already got Paris to 28 and Bangkok to 17 price-bearing chunks. The
*opportunity* was real and much larger than the stated symptom, but the premise as written
was out of date. Re-measure before trusting a filed motivation.

**Not done:** this is ingestion-time only, so it changes nothing until destinations are
re-ingested — a data run that has **not** been performed.

---

### v10.50.0 Changes (July 2026) — unified ingestion metadata schema (#33), India itinerary seeds (#47), and #36 closed as already-built

Suite **951 passed / 6 skipped** (`pytest tests/`, the command CI runs), up 34 from
v10.49.0's 917; ruff clean, mypy clean on all touched modules.

> ⚠️ **Measurement note, since this bit me while writing this entry.** v10.49.0's §14 text
> quotes **883** and README quotes **917** for the same commit. Both are correct and neither
> is the other's error: `pytest tests/unit` is 883 and `pytest tests/` (unit + the 6
> integration files, which is what `.github/workflows/ci.yml:94` runs) is 917. **Quote the
> full-suite number and say which command produced it** — an unqualified count is ambiguous
> here, and the two scopes happen to differ by exactly the 34 tests this release adds, which
> is precisely the coincidence that makes it easy to misread.

**#33 — unified metadata schema.** New `core/ingestion_metadata.py::build_ingestion_payload()`;
`scrapers/{osm,wikivoyage,reddit,youtube_comments,youtube_narration}.py` all build payloads
through it instead of hand-rolling a dict. Adds `source_name`, `country`, `content_type`,
`language`, `quality_score`, `ingested_at`, and optional `published_date`/`attraction_type`
to sources that previously carried only `destination`/`source`/`text`/`source_url`.

**Two deliberate deviations from `docs/rag-strategy.md` §11 as written, and §11 is now
corrected rather than left disagreeing with the code:**

1. **`text`/`source_url`, not the spec's `content`/`url`.** Every scraper *and every reader*
   (`core/cost_grounding.py`, `services/gems.py`, `services/search.py`,
   `core/price_extraction.py`) has always used the former, as does all live cluster data.
   Renaming meant re-ingesting every collection *and* rewriting every consumer for zero
   behavioural gain. The spec was written ahead of the code; the code's names win.
2. **`attraction_type` gains `"landmark"`.** §11's seven values have no bucket for a
   monument, castle, ruin, memorial or place of worship — together the largest slice of the
   OSM corpus. Forcing them into `"activity"` would defeat the precision filtering the field
   exists for. Extending the vocabulary is honest; silently mis-bucketing is not.

**Cutover point:** pre-2026-07-29 points carry only the four legacy fields, so every added
field is **optional at read time** — consumers must `.get()` with a default. Backfilling the
existing corpus is a data run, not a code change, and has **not** been done.

`language` is Devanagari-aware by **presence, not ratio**: Hinglish mixes scripts freely
("Jaipur ka khana ₹200 me मिल जाता है") and a ratio threshold would file exactly those chunks
as English and hide them — the same class of failure v10.41.0 paid for when `\b` silently
failed on Devanagari. A test pins that `₹` (U+20B9) is *outside* the U+0900–U+097F block, so
an English chunk quoting a rupee price stays `en`.

**#47 — 2 more India itinerary seeds**, taking `WIKIVOYAGE_ITINERARY_TITLES` from 3 of 7
India-specific to 5 of 9: `Grand Trunk Road` and `Buddhist Circuit`. Live-verified through the
real `scrape_wikivoyage_itinerary()` rather than a proxy predicate, **then** cross-checked
against `action=query&prop=categories` — both sit in Wikivoyage's own `Category:Itineraries`
and `Category:South Asia itineraries`. 🔴 **That second check is what earned its keep:**
`Kashmir Valley` returned more content than any other candidate (13,582 chars, twice the
accepted two) but is `Category:Region articles` — it would have passed a
content-length-only bar and quietly seeded a region guide into an itinerary corpus.
`Char Dham` and `Coastal Karnataka` both silently redirect away from the requested title.
Incidental finding recorded rather than acted on: two *pre-existing* entries are not
itineraries either (`Kerala Backwaters` is a region, `Rail travel in India` a travel topic),
so the two added here clear a higher bar than the list they joined.

**#36 — closed as already implemented, no code written.** The issue asked to add a second
named vector to `itinerary_corpus` "which currently retrieves using a single embedding". It
does not: `core/qdrant.py:74-81` creates named `config` + `content` vectors,
`chains/itinerary_corpus_extraction_chain.py:260` writes both, and
`services/search.py:456-493` searches both and merges 60/40 with `quality_score` weighting —
which is the issue's own acceptance criteria, already met. **Recorded because the cost of
re-verifying a premise is a few minutes and the cost of not doing so was a duplicate
implementation of a shipped feature.**

**Tests:** `tests/unit/test_ingestion_metadata.py` (31) and
`TestWikivoyageItinerarySeedList` (3). Two are deliberately structural rather than
behavioural: one asserts every `source` string the scrapers actually write is present in
`SOURCE_CONTENT_TYPE` (the only failure mode of that map is silent fallthrough to the
default), and one pins `OSM_POI_TYPE_TO_ATTRACTION`'s keys against the real
`POI_TAG_QUERIES` values, since a typo there never raises — it just never matches.

---

### v10.49.0 Changes (July 2026) — venv/httpx pin fixed, Qdrant headroom monitored, share links + travel tips moved onto Redis

**Local dev environment, live-reproduced this session:** `apps/api/.venv` had drifted to
Python 3.9 (a bare `python3 -m venv .venv` picking up the macOS Command Line Tools stub),
which fails on `datetime.UTC` (3.11+) deep inside `core/scheduler.py` with a cryptic
`ImportError`. Fixed with a `sys.version_info < (3, 11)` guard as the literal first lines
of `main.py` (before any other import), an explicit Python-3.11+ warning added to
README's setup instructions, and `requirements-dev.txt`'s `httpx==0.27.0` bumped to
`0.28.1` to match `requirements.txt` (was silently divergent). `.venv` rebuilt clean on
Python 3.12; full suite re-verified at that point: **883 passed / 6 skipped**.

**Qdrant Cloud free-tier 1GiB headroom monitored** (`core/qdrant.py::estimate_storage_usage()`,
`core/scheduler.py::_check_qdrant_storage_headroom()`, daily) — logs WARNING/ERROR past
70%/90% of the cap, surfaced on `/admin/metrics/summary`. **Self-correction, same day:** the
first version estimated vector bytes from dimensions (`points × dims × 4 bytes`) and came
out ~70MiB, **4.4x under** the ~304MiB the real Qdrant Cloud console showed for the
identical corpus (System 104.90MiB + Cache 171.59MiB + Data 27.96MiB, ~39,862 points) —
real per-point RAM cost is dominated by HNSW index/cache overhead, not raw vector floats.
The estimator now uses a flat ~8KiB/point figure back-derived from that live console
measurement, verified afterward to land within ~2% of it.

**Share links + travel-tips cache moved from plain in-process `dict`s to Redis**
(Railway's "Redis" template, deployed 2026-07-29 — available on all Railway plans
including free/Hobby, 5GB volume cap; billed as ordinary usage, not a separate line item).
`docs/scaling-tech-challenges.md` had flagged both as a correctness bug (all data lost on
every restart/deploy, would be inconsistent across any future multiple instances) and a
memory-leak risk — the travel-tips cache's own docstring claimed "1h cache" but never
actually checked an expiry. New `core/redis_client.py` exposes `get_json`/`set_json`/
`delete`/`flush` with a real TTL (90 days share links, 1 hour travel tips), backed by
Redis in production and an in-process dict fallback locally when `REDIS_URL` is unset —
local dev never requires standing up Redis. Verified live end-to-end: created a share
link, killed and restarted the local API process, confirmed the link still resolved (the
exact bug class this fixes) — then confirmed a lowered memory ceiling correctly triggers
the auto-flush path described below and the link 404s afterward as expected.

**Redis memory monitored with an automatic ceiling, not just a log line**
(`core/scheduler.py::_check_redis_memory_headroom()`, every 6h) — logs WARNING past 70%
of a configurable 256MiB ceiling and, unlike the Qdrant check, **flushes the cache
outright** past 100%. Deliberately more aggressive than the Qdrant check because
everything in this Redis instance is disposable/derived (share links, tips), not
source-of-truth data — a full flush is a safe, cheap recovery from unexpected growth
(e.g. a key-explosion bug) rather than something needing careful selective eviction.
Same numbers (used-MB, key count) surfaced on `/admin/metrics/summary`.

**Found, not fixed:** `services/geocode.py::_cached_geocode()` is `@lru_cache`-decorated
but its body unconditionally `return None`s — despite the module's own docstring (and
`docs/scaling-tech-challenges.md`) describing a working "geocode cache," it has never
actually cached a real result; every `geocode_city()` call hits Nominatim live. Left out
of scope for this pass; flagged for a future fix that should wire it into this same Redis
layer rather than reintroducing an in-process `lru_cache`.

**Stale docs deleted:** `KNOWN_ISSUES.md` (June 18) and `BUG_FIXES_SUMMARY.md` (June 17)
both referenced `ConversationalWizard.tsx`, removed months ago and replaced by
`LLMWizard.tsx`; every "pending" item in them had since shipped or no longer applied.

Backend **917 passed / 6 skipped** (rebuilt `.venv`, Python 3.12); ruff + mypy clean on
all touched files.

### v10.48.0 Changes (July 2026) — Voice-mic states redesigned, full E2E accessibility pass, zero backend impact

Two live user reports on voice mode, followed by a full read-only `ui-ux-pro-max` audit
of every surface (landing, auth, wizard, dashboard, itinerary, account, admin, layout/nav,
voice, comparison) — fixed **every** finding rather than a top-priority subset, then
verified no backend regression and measured the frontend cost. Full findings write-up:
`docs/UI_UX_AUDIT_2026-07-29.md`. Design-system framing: `DESIGN_REVAMP_SUMMARY.md` (July
29, 2026 section).

**Voice mode, reported as issues [#30](https://github.com/kunalsmathur-gif/wanderplanner/issues/30) / [#31](https://github.com/kunalsmathur-gif/wanderplanner/issues/31):**
- 🔴 **Persistent language toggle clipped the mic icon on mobile.** `LLMWizard.tsx`'s
  header English/हिंदी toggle and the mic button competed for the same row below `sm:`,
  and on narrow viewports the mic lost. Removed the persistent toggle; added a one-time
  overlay prompt shown only on the first voice activation per session
  (`voiceLangAskedRef`), gated through a new `handleChooseVoiceLang`. Relies on
  `useVoice.ts`'s `setLang` updating `langRef.current` synchronously, so calling
  `voice.setLang(next)` immediately followed by `voice.toggleVoiceMode()` in the same
  handler picks up the new language with no stale-closure risk.
- 🔴 **The mic button had one visual state (red, slash icon) for idle/active/unsupported
  alike** — indistinguishable from broken. Both mic buttons (header pill + footer bar) now
  render `Mic` (grey, idle) / `Mic` with `animate-pulse` (active/listening) / `Volume2`
  (Anya speaking) / a visibly disabled control (unsupported browser, e.g. Firefox — the
  button previously did nothing on click with zero feedback).
- ⚠️ **Follow-up from the same user: "is red really the right active color?"** — asked to
  use `ui-ux-pro-max` rather than pick another color by feel. Queried the skill's palette
  data against this app's own tokens (`apps/web/app/globals.css`): `--_destructive` (red)
  is reserved app-wide for genuine errors, and a `--_success` (emerald) token already
  exists for positive/active states. Surveyed top-chatbot conventions as reference (ChatGPT
  — green ring; Gemini — non-red pulse; Siri — non-red color wash): none use red for
  "actively listening," it reads as "stopped/broken" instead. Changed the active state to
  `emerald-400`/`emerald-950` (Tailwind fixed classes, not the `--_success` var itself,
  chosen to guarantee contrast in both themes without adding a new on-color token).

**Full E2E pass — asked to fix every finding, not the top 5:**

| Area | Representative fixes |
|---|---|
| Landing + wizard | `<img>` → `next/image` (added `images.remotePatterns` for `upload.wikimedia.org`); "Plan this" CTA no longer hover-only invisible; extract-error banner now `role="alert"`; previously-dead `FEATURES` array now rendered as a "How it works" section; wizard modal gained a full focus trap + Escape-to-close + focus-return (`dialogRef`/`previouslyFocusedRef`/`handleDialogKeyDown`); both progress bars gained `role="progressbar"` ARIA; icon buttons/chips bumped to the 44px tap-target minimum. |
| Auth (login/signup/forgot/reset) | `aria-invalid`/`aria-describedby` wired to field errors; password-toggle + consent-checkbox tap targets enlarged; `returnTo` now survives the forgot-password → reset-password hop via `useSearchParams` + `sessionStorage`. |
| Dashboard + chat | `BookingHub` tabs given visible labels, delete control always focusable (was hover-only); `BestTimeWidget` gained non-color-only best/avoid cues at larger text; `ChatPanel` responsive (`inset-x-4 bottom-4` mobile → `w-[360px] right-6 bottom-24` at `sm:`). |
| Itinerary view | Removed nested-interactive pattern in `ItineraryTimeline`/`PolaroidCard` (single `button`); `next/image` for timeline/sidebar thumbnails (`img.youtube.com` added to remote patterns — this and the wikimedia pattern above were added by different parallel agents and had to be merged, not overwritten); fixed an empty-origin "→ Destination" string in `BookingLinksSection`. |
| Account + admin | Labeled the type-to-confirm delete/purge inputs; admin usage chart gained horizontal-scroll + text-legend + compact-table fallback. |
| Layout + voice | `UserMenu` gained full focus management (first-item focus, Escape, arrow/Home/End nav, focus-restore) + new tests; `ListeningOrb`'s near-invisible red listening dot replaced with a visible green status pill, animation made `prefers-reduced-motion`-safe. New test files: `__tests__/components/UserMenu.test.tsx`, `ListeningOrb.test.tsx`. |
| Comparison | `DestinationSearchInput` gained full combobox/listbox ARIA + keyboard nav; `ComparisonPanel` reflows `grid-cols-1 sm:grid-cols-2`; `ComparisonGrid`'s label column made sticky. |

**Regression + performance check, done because every change above is UI-only:**
- **Backend: zero files touched** (`git diff apps/api` empty) — confirms no latency/cost/flow
  regression is even possible from this pass. Ran the full suite anyway on a rebuilt Python
  3.12 venv (the committed `.venv` is 3.9, incompatible with `datetime.UTC`): **917 passed,
  6 skipped**. Re-ran `tests/unit/test_itinerary_timing.py` (v10.47.0's instrumentation)
  in isolation — **22/22** — to confirm the LLM-latency measurement path itself wasn't
  disturbed. Did **not** run `load_test_rag.py` (needs live Gemini/embedding keys, real
  cost, and nothing backend changed for it to catch).
- **Frontend: `tsc --noEmit` clean; `vitest run` 126 passed** (10 files, incl. the 2 new
  ones above). Real before/after `next build` (fixes stashed vs. applied, identical 14
  routes both times): client JS **2,944,818 B → 2,962,893 B raw (+0.6%)**, **937,680 B →
  943,306 B gzip (+0.6%)** — fully attributable to the added a11y logic (focus trap,
  combobox keyboard handling, extra legend/label markup); `package.json`/lockfile diff
  empty, so none of it is a new dependency. `next/image` conversions (landing,
  `PolaroidCard`, `Column3Sidebar`) don't show up in that static diff but should reduce
  real transferred image bytes and improve LCP at runtime.

**Filed, not fixed — pre-existing repo hygiene, found incidentally:** the committed
`apps/api/.venv` targets Python 3.9 while the code requires ≥3.11; `requirements.txt` pins
`httpx==0.28.1` while `requirements-dev.txt` pins `httpx==0.27.0`.

### v10.47.0 Changes (July 2026) — `generate_itinerary()` is measured for the first time

`docs/scaling-tech-challenges.md` had carried "No observability stack" as an
open finding for months. The specific gap, confirmed by grep: **zero
`time.time()` or `perf_counter` calls anywhere in `chains/` or `routers/`.**
Every latency claim in these docs — the cold-start ingestion cost, the retry
cascade, the Pexels fetch, the "each refinement stacks onto the critical path"
worry — was static reasoning about code, never a measurement.

New `core/timing.py` records per-stage wall-clock against a `ContextVar`, so
`chains/itinerary_chain.py` did not need six function signatures changed to
thread a timer through. One structured record per generation, at INFO, or at
**WARNING past `slow_itinerary_threshold_seconds`** — the cheapest useful
alerting available without an APM, since the level is the signal and the
per-stage breakdown rides along to say which stage caused it.

**A prerequisite bug, found while building it: `JsonFormatter` silently dropped
`extra=`.** It emitted only timestamp/level/logger/message, so structured fields
logged that way reached no sink at all — the instrumentation would have produced
nothing. `RedactionFilter` had the matching hole: it redacts `getMessage()`, and
structured values ride *beside* the message, so they went out unredacted. Same
blind spot as the v10.40.3 state-file leak, where the log line was covered and
the value written next to it was not.

#### The measurements, and what they refute

Two live end-to-end generations, real Gemini + real Qdrant Cloud:

| stage | Jaipur | Paris |
|---|---|---|
| **total** | **62.6s** | **48.0s** |
| `llm_api` | 35.6s (57%) | 41.7s (87%) |
| `rag_retrieval` | 20.9s | 2.8s |
| `unaccounted` | 3.9s | 1.6s |
| `guidance_blocks` | 1.4s | 1.1s |
| `cache_store` | 0.7s | 0.8s |
| `ingestion` | 0.03s | 0.03s |
| `post_processing` | 0.0013s | 0.0010s |
| `photos` | 0.0003s | 0.0002s |

- ✅ **The "every new refinement stacks onto the same critical path" concern is
  measurably dead.** Scoring, persona injection, pin enforcement and
  `generation_tier` together cost **1.3 milliseconds**. That worry had been
  filed against real growth in that block, and it was wrong.
- 🔴 **Jaipur's 20.9s retrieval is not a slow destination — it is one-time model
  load, and I checked rather than assuming.** Isolating retrieval with no LLM
  call: cold process 20.0s → warm 1.4s → Paris 2.2s → Jaipur again 1.45s. Real
  per-call cost is 1.4–2.2s. But the ~18.6s is genuinely paid by **the first
  request after every deploy**, and Railway redeploys on every push — a real
  production effect that had never been named. It is distinct from *destination*
  cold-start ingestion, which is the one the docs did name.
- ⚠️ **The `photos` number is worthless and is not evidence.** `PEXELS_API_KEY`
  is absent from local `.env`, so `get_day_photo()` returns at its
  `if not settings.pexels_api_key` guard — 0.3ms is the no-key short-circuit,
  not a fetch. The key *is* set on Railway, so in production that 6-second
  awaited timeout genuinely fires and **remains unmeasured**. Deploying this
  instrumentation is what will answer it. (The TODO's claim that the key is "set
  locally and on Railway" is wrong about local; corrected there.)

#### 🔴 The retry cascade cannot fit inside the request timeout

Not a timing measurement — an arithmetic one, and it holds regardless of load.
`_gemini_itinerary`'s backoff is `min(5 * 2**attempt, 60)` applied after every
attempt but the last: **5+10+20+40 = 75 seconds of sleeping per model**, before
the first model gives up. `routers/itinerary.py` wraps the entire call in
`asyncio.wait_for(..., settings.llm_timeout_seconds)`.

That timeout is **30s by code default, and 120s in both local `.env` and Railway
production** — checked, not assumed, because a Railway variable overrides a code
default and this project has been bitten by exactly that before
(`NOMINATIM_USER_AGENT`, v10.38.x). Even at 120s, one model's backoff eats 62%
of the budget and the full three-model cascade needs 225s.

**The consequence is worse than slow requests:** `_fallback_itinerary()` — the
cache → RAG-skeleton → mock ladder that exists precisely for a failing provider —
is only reached once *every* model is exhausted. Under sustained transient
errors the request is cancelled mid-cascade and the user gets `LLM_TIMEOUT`
instead of the degraded-but-real itinerary. **Deliberately not "fixed" here:**
the options (shorter schedule, a deadline threaded into the cascade, fewer
attempts) are a product call, and making it before the instrumentation reports
how often transient errors actually occur would be another guess. The arithmetic
is pinned by test and documented at the `max_attempts` definition.

`tests/unit/test_itinerary_timing.py` — 22 tests. Suite **883 passed / 6
skipped**, ruff + mypy clean (180 files).

### v10.46.0 Changes (July 2026) — The four deferred enum fields are closed sets at last, plus a doc-accuracy sweep

Two carried items, both filed as small and both a little larger than filed.

**1. `pace` / `scope` / `crowd_preference` / `destination_mode` are now
`Literal`s.** v10.43.0 bounded every user-supplied string but deliberately left
these four as free `ShortLabel`s, because they are populated from the wizard
LLM's `config_patch` — a bare `Literal` would have turned a casing mismatch
(`"Moderate"`) into a hard 422 in the middle of a conversation. The fix is the
order the TODO specified: **normalise first, then constrain.**

`core/validation.py` gained a per-field vocabulary (canonical values + alias
map), `normalise_choice()`, and `Annotated[Literal[...], BeforeValidator(...)]`
types. Because the `BeforeValidator` runs pre-validation and can only emit a
member of the set, the `Literal` is satisfied by construction rather than by
hope. It absorbs the three ways a model realistically deviates: **casing**
(`"Moderate"`), **decoration** (`"off-beat"`, `"Off Beat!"`, `"off_the_beaten_path"`)
and **synonyms** (`"slow"`, `"abroad"`, `"undecided"`, `"multi-city"`).

> ⚠️ **Unrecognised values fall back to the field default and log a WARNING —
> they are not rejected. This is a deliberate exception to `core/validation.py`'s
> "reject, never coerce" rule**, and the justification is that the *producer* is
> different: everywhere else in that module the producer is a user, whose bad
> input should fail visibly, but here it is our own prompt, and a 422 would
> charge the user for our drift. The WARNING is what stops it being silent — a
> missing alias surfaces in logs instead of in a quietly reshaped trip.

> ⚠️ **The alias maps are per-field on purpose and must not be merged.**
> `"moderate"` is a canonical `pace` *and* an alias for `crowd_preference:
> "balanced"`. One shared map would silently make one of those wrong. A test
> pins both readings.

**The part that wasn't in the filed scope:** doing this only at the model layer
would have fixed almost nothing in practice. `config_patch` is merged into the
running `partial_config` as a **plain dict** and handed back to the frontend
store — it never passes through `TripConfig` during the conversation. Worse,
`wizard_chat_chain.py` branches on exact values throughout
(`mode == "fixed"`, `!= "exploring"`), so a stray `"Moderate"` or `"undecided"`
would have steered every remaining turn before the generate call ever validated
it. And `apps/web/types/index.ts` declares all four as TypeScript unions, which
are **erased at runtime** — the frontend would have believed it. So
`normalise_choice_fields()` is applied at the patch-merge point in
`wizard_chat_chain.py` *and* in `chat_refine_chain.py`, whose patch goes
straight into `ChatPanel.tsx::updateConfig`.

`tests/unit/test_choice_normalisation.py` — 51 tests, including guards that no
alias targets a non-canonical value, no alias shadows a canonical one, and no
alias key is written in a form the normaliser could never produce (dead entry).
Suite **861 passed / 6 skipped**, ruff + mypy clean (178 files).

**2. Doc-accuracy sweep — two known items, five real ones.** The TODO carried
two stale claims. Enumerating instead of fixing the two named turned up three
more, all of the same "current-state claim that stopped being true" kind:

- 🔴 **`docs/scaling-tech-challenges.md` still described `:memory:` Qdrant as the
  live architecture** and carried three open risk rows saying it "must be fixed
  before any multi-instance deployment" — a *risk assessment* telling the reader
  an already-completed migration was outstanding. Marked resolved with a dated
  banner; findings kept in place because the reasoning still applies to the
  genuinely-unresolved in-process state (share store, caches, per-process quota
  window).
- 🔴 **`docs/rag-strategy.md` still carried a claim v10.40.3 retracted** — that
  the cold-start gate over-subscribes the `search.list` cap on its own. It does
  not; every cold start consults the budget before spending. Three docs were
  corrected at the time and this one was missed. Annotated as a second
  correction rather than rewritten, since it corrects a correction.
- 🔴 **`docs/PRD.md` §6.1 still called the YouTube Data API path "planned (not
  yet built)"** and described Reddit as an active scheduled source. That path
  shipped in v10.30.0 and covers all 170 destinations.
- The architecture diagram in `docs/system-design.md`, the tech-stack table in
  this file, and `README.md`'s `QDRANT_URL` row (which now documents
  `QDRANT_API_KEY` too) all said in-memory.
- `README.md` also still documented `YOUTUBE_DAILY_SEARCH_BUDGET`'s default as
  80; it has been 100 since v10.40.1. The "10,000 units/day" non-binding quota
  was corrected there and in `DEMO_DAY_FAQ_CHEATSHEET.md`,
  `scaling-tech-challenges.md`, `core/config.py` and
  `scrapers/youtube_comments.py`.

⚠️ **New item this raised, filed not fixed:** the Qdrant Cloud **free tier is
1GB and nothing monitors headroom against it**. `youtube_comments` alone is
~25k points across 172 destinations, with `youtube_narration` growing beside it.
The first symptom of hitting the ceiling is write failures mid-ingestion.

### v10.45.0 Changes (July 2026) — Voice mode had never spoken, and Anya now speaks Hindi

Voice was the last feature in the product with **zero tests of any kind**. The
six frontend test files covered stores and formatters; none touched voice, the
wizard, or `ListeningOrb`. Reading the code turned up four defects, and writing
the tests turned up a fifth that was larger than all of them.

**🔴 Text-to-speech had never run in production. Not once.** Two independent
bugs, either of which alone is enough:

1. `toggleVoice()` assigned `rec.onresult = () => handleSubmit(...)` and *then*
   called `setVoiceActive(true)`, so the handler held the `handleSubmit` — and
   transitively the `sendMessage` — from the render where the flag was still
   `false`. `sendMessage`'s `if (voiceActive) speak(res.reply)` therefore read
   `false` on every voice-driven turn.
2. A single `voiceActive` flag stood for both "the user wants a spoken
   conversation" and "the mic is open". `rec.onend` fires the moment the user
   stops talking, so it cleared the mode seconds before the API replied — even
   a fresh read would have been `false`.

**This was verified by execution, not by reading.** The previous implementation
was reconstructed structurally in a throwaway test and driven through the real
event order: the reply arrived, and `speak` was never called. That step is
deliberate — this project has three recorded instances of a causal claim being
propagated into docs before it was measured.

**🔴 Text-to-speech also stripped Devanagari entirely** — the fifth bug in this
codebase's character-rule family, after `core/keyword_match.py` (substring
false positives), `\b` failing on matra-final Hindi words, and
`core/validation.py`'s ZWJ/ZWNJ handling. The allowlist was
`[^\w\s.,!?'₹%-]`, and **JavaScript's `\w` is always ASCII `[A-Za-z0-9_]`; the
`u` flag does not change it**. Every Devanagari character was removed, `clean`
became empty, and the next line's `if (!clean) return` produced silence. `₹`
had been whitelisted explicitly, so India was in mind — just the currency, not
the script.

The replacement allowlist is keyed on Unicode categories, and two of its
entries are the whole point:

| Kept | Why |
|---|---|
| `\p{M}` | Devanagari vowel signs are **combining marks, not letters**. `खाना` is ख + ा + न + ा; `\p{L}` alone yields `खन` — a real word meaning something else, spoken confidently. Half-fixing this is worse than not fixing it, because silence is at least obviously broken. |
| `।` | The danda is the Hindi full stop. Allowing `.` but not `।` runs every Hindi sentence into one flat utterance. |
| ZWJ / ZWNJ | Load-bearing in conjuncts. `core/validation.py` preserves them through backend normalisation; stripping them here would undo that one layer later. |

Because ZWJ now survives, an emoji-only reply cleans down to bare invisible
joiners — non-empty to a truthiness check, silent to a synthesiser. The
sanitiser therefore requires at least one letter or digit, mirroring the rule
`core/validation.py` already applies to place names.

**Three smaller defects, all fixed.** The mic button was rendered
unconditionally but `toggleVoice` did `if (!Ctor) return`, and **Firefox has
never shipped `SpeechRecognition`** — a click produced no state change and no
message, a completely dead control. Every recognition failure collapsed into
`rec.onerror = () => setVoiceActive(false)`, so denying microphone permission
looked exactly like pausing mid-sentence; the six error codes now map to
distinct messages, with `aborted` deliberately silent because it is our own
`stop()`. And `getVoices()` was read at speak time, but Chrome returns `[]`
until it fires `voiceschanged` — with no listener anywhere in the file, the
first utterance of every cold session fell through to the platform default
voice, which is the one that sets the tone.

**🔴 Anya was speaking in a male voice.** The persona is a woman; the voice
preference matched `/female/` in a voice name; **no platform puts it there.**
Measured on the dev machine's real voice list, `pickVoice(voices, 'en-IN')`
returned **Microsoft Ravi** — with Heera sitting immediately beside him in the
same array — because neither name says "female" and the rule fell through to
array order.

**The Web Speech API has no gender field.** `SpeechSynthesisVoice` is `name`,
`lang`, `default`, `localService`, `voiceURI` and nothing else. The OS *does*
know: every Windows voice token carries `Attributes\Gender` in the registry,
verified as `Female` for Heera and `Male` for Ravi. That information is
discarded at the browser boundary, so curated name lists are not a shortcut
around a real API — they are the only lever that exists. Selection now scores
each candidate on language first and gender second, covering the voices
Windows, Apple and Edge ship for `hi-IN` (Kalpana, Lekha, Swara vs. Hemant,
Neel, Madhur) and `en-IN` (Heera, Veena, Neerja vs. Ravi, Rishi, Prabhat). An
unrecognised name scores **neutral and is still used** — deliberately, since
not recognising a voice costs the wrong gender while refusing it costs silence.
Language always outranks gender: a Hindi line read by an English voice is
unintelligible, whereas the wrong gender is merely off-persona.

**The missing-voice notice fires at language selection**, not on Anya's first
reply. Discovering three turns in that the device cannot speak Hindi is worse
than being told when you pick it. A selection made before `voiceschanged` has
fired cannot be judged — `getVoices()` is empty then, which means *unknown*
rather than *absent* — so the check re-runs when the real list arrives.
Explicit re-selection always re-answers, while the automatic re-checks
deduplicate, because silence in response to a deliberate tap reads as "it works
now".

**⭐ NEW — Hindi voice input and output.** `rec.lang` was hardcoded `en-IN`,
which tells the recogniser to expect Indian-accented *English*; speaking Hindi
at it returns garbled English guesses, never Devanagari. The Web Speech API has
**no auto-detect** — recognition takes exactly one language per session — so
this is an explicit English / हिंदी toggle in the wizard header rather than a
smarter default. It drives recognition language, utterance language and voice
selection together.

`WIZARD_SYSTEM_PROMPT` gained section 3a: mirror the user's language in
`reply`, and **only** in `reply`. Section 3 had always handled Hinglish *input*
("Mumbai se Bali 7 days mein") but said nothing about output. The asymmetry is
deliberate and load-bearing in both directions:

- **`chips` stay English.** `LLMWizard.tsx` classifies chip groups by matching
  English keywords, so a translated chip does not fail visibly — it silently
  turns a multi-select theme group into single-select, which is a bug the file
  already carries a comment about having shipped once.
- **`config_patch` stays English, Latin script.** A destination is a database
  key: geocoded, ingested and cached under its English name. "गोवा" and "Goa"
  would become two unrelated destinations, and the Hindi one would trigger a
  whole redundant cold-start ingestion of data already held.

Typed Devanagari already worked end to end and this was confirmed by
measurement rather than assumed from `core/validation.py`'s docstring:
`clean_user_text` round-trips Hindi byte-identically, including conjuncts and
embedded ZWJ, and the pydantic models accept it.

**Structure.** Voice moved out of the 959-line `LLMWizard.tsx` into
`apps/web/lib/voice.ts` (pure: sanitiser, voice selection, error mapping,
capability detection, the language table) and `apps/web/hooks/useVoice.ts`
(state and Web Speech wiring), matching how `lib/format.ts` and `lib/limits.ts`
are already tested. `voiceMode`, `isListening` and `isSpeaking` are now three
separate things; `isSpeaking` had been set in three places and read in none, so
there was no speaking indicator anywhere. The mic re-arms after Anya finishes
speaking and **only** from the utterance's own `onend`, never while audio is
playing, so an open mic cannot transcribe Anya back into the conversation.

**Mobile is where this gets least verifiable, so it is instrumented rather
than assumed.** Android and iOS are the bulk of the user base and neither can
be measured from a dev box:

- **Android defeats name matching entirely.** Google's TTS voices arrive as
  `"Google हिन्दी"` — no personal name, no gender token — so nothing in the
  curated lists can match and selection falls through to whatever the platform
  lists first. In practice Android usually exposes one voice per language, so
  there is no choice to make and Google's Hindi default happens to be female.
  That is the platform landing right, not this code getting it right, and the
  distinction is worth keeping honest.
- 🔴 **iOS Safari only permits `speechSynthesis.speak()` from inside a user
  gesture, and Anya's first utterance arrives after an awaited API call** —
  long past the tap that started voice mode. That would be silence on iPhone
  regardless of voice selection. `useVoice` now speaks a zero-volume space
  synchronously inside the toggle handler, which unlocks the synthesiser for
  the session. **Not verified on a real device** — it is defensive, based on a
  documented WebKit constraint, and free everywhere else.
- **`/dev/voice` is a new on-device diagnostic** (`app/dev/voice`, `noindex`).
  It lists every voice the device reports with its `voiceURI` and the guessed
  gender, shows which one `pickVoice` selects for each language and why, and —
  the part no unit test can cover — speaks *after a delay with no gesture on
  the stack*, reproducing exactly how a real reply arrives. It emits a
  copy-pasteable report, so the curated lists can be corrected from real
  device data rather than extended by guessing.

On the dev machine the page agrees with the OS registry on **all five voices**
(David/Ravi/Mark male, Heera/Zira female), selects Heera for `en-IN`, reports
no `hi-IN` voice, and passes the delayed-speech test — the expected desktop
baseline, since the gesture restriction is a WebKit behaviour.

**Tests: 122 frontend (was 44) and 844 backend (was 830).** Ruff, mypy and
`tsc --noEmit` clean.

**Honest residuals, measured not guessed:**

- 🔴 **The dev machine has no `hi-IN` voice installed** — `getVoices()` returns
  five voices, all `en-US`/`en-IN`. Hindi *recognition* still works (Chrome
  routes it to a cloud service), but Hindi *speech* needs a Windows Hindi
  language pack. This is the expected desktop case, not an edge case, which is
  why the hook checks voice availability up front and says so rather than
  waiting for a `language-unavailable` event that several browsers never fire.
- **English-in-`config_patch` is a prompt-level guarantee, not an enforced
  one.** `CityName` accepts `"गोवा"` — verified — so nothing downstream stops a
  Devanagari destination reaching geocoding. Enforcing it needs transliteration
  or a lookup, and is not built.
- **`_strip_leaked_reasoning` does not fire on Hindi replies.** Pass 1 matches
  English warm openers; pass 2 splits on `[.!?]`, which a danda-terminated
  sentence never matches. It degrades to "return unchanged" — the safe
  direction — so leaked reasoning in a Hindi reply would reach the user. In
  practice leaks are English-shaped, because the model reasons about our
  English field names, and that case still strips correctly.
- The curated female-voice list (below) covers the voices Windows, Apple and
  Edge are known to ship for `hi-IN` and `en-IN`. It is a best effort, not a
  registry: an unrecognised name scores neutral and is still used, because
  not recognising a voice costs the wrong gender while refusing it costs
  silence.
- UI chrome stays English when हिंदी is selected. The toggle is scoped to
  voice, and labelled that way, but full interface localisation is a separate
  piece of work.

### v10.44.0 Changes (July 2026) — A derived name core has to be a name, not a word

`services/name_matching.py` builds the surface forms of a POI name that a
traveller might type. Peeling the structural word off "Egyptian Museum" leaves
the bare token `egyptian`, and the guard meant to catch that was a length
threshold: a derived single token had to be 8+ characters. `egyptian` is 8.

**The threshold cannot be raised out of the problem, which is what made this
worth doing properly.** `immanuel` — the genuine recovery from "Fort Immanuel",
recorded in the module's own docstring — is also exactly 8. Length was never
the real question; it was a proxy for *is this token an ordinary English word
or is it specific to this place?* The fix asks that question directly.

**🔴 The reported scope was a tenth of the real one.** The item was filed from
one observation: Cairo's Egyptian Museum showing 30 mentions, 29 of them from
the bare token. Measuring the whole corpus first (9,892 POIs, all 168
destinations) showed `egyptian` is a mid-sized instance of a much larger class
— **every POI whose name begins with its own city**, in that city's own
corpus, where the city name is by construction the most frequent token there:

| POI | mentions before | after |
|---|---|---|
| Singapore City Gallery | 100 | 1 |
| Singapore Zoo | 100 | 2 |
| Edinburgh Castle | 84 | 2 |
| Melbourne City Synagogue | 61 | 2 |
| Melbourne Museum | 59 | 0 |
| Melbourne Park | 59 | 0 |
| Museum of Copenhagen | 62 | 5 |
| Amsterdam Museum | 49 | 0 |
| Valencia Cathedral | 47 | 0 |
| Egyptian Museum | 30 | 1 |
| Grand Egyptian Museum | 29 | 0 |

(100 is the mention ceiling, so the two Singapore entries were saturated.)
Melbourne is the clearest illustration: three different POIs were each
independently credited with the destination's entire comment volume.

**The word list.** A token that survives in a 30,522-entry WordPiece
vocabulary *as a whole word*, rather than being split into fragments, is by
construction a frequent English word — that vocabulary is built by frequency
over Wikipedia and BooksCorpus. `core/embeddings.py` already loads the model
that carries it, so `scripts/generate_common_words.py` extracts the 8,366
whole words of 8+ characters into `services/data/common_english_words.txt`,
which is committed. **The runtime path reads a text file and never loads a
model** — `name_matching.py` stays pure-CPU, as its docstring has always
claimed. The length guard is kept as a cheap first gate, so both rules apply.

Of 521 distinct derived single-token cores in the corpus, **144 are common
words** and are now rejected. They fall into two groups, both matching things
that are not the POI: ordinary words (`national` — 20 POIs — `botanical`,
`government`, `parliament`, `auditorium`, `military`) and place names at the
wrong scale (`egyptian`, `japanese`, `melbourne`, `singapore`, `edinburgh`,
`kensington`).

**A second guard, in `services/gems.py`, because the word list cannot close
the class.** A destination absent from the vocabulary — Queenstown, Hoi An,
Abu Dhabi, Chiang Mai, Rio de Janeiro, Kuala Lumpur, Marrakech — still had its
POIs peeling down to the bare town name. Only `compute_gem_intel_sync` knows
which destination it is looking at, so that is where a variant equal to the
destination is dropped. It sits directly beside the existing rule that
excludes a POI *named* the destination: same mis-attribution, one word wider.
It accounted for 14 of the 58 matched-POI removals on its own.

**Measured across all 168 destinations** (the committed
`scripts/audit_gems.py`, against the committed post-v10.42.0 baseline; the
corpus was not re-ingested in between, and `n_candidates` is identical at
9,556 in both runs, which is the control that says only matching changed):

| | baseline | word list | + destination guard |
|---|---|---|---|
| total matched POIs | 530 | 486 | **472** |
| crowd favourites | 87 | 64 | **50** |
| total gems | 172 | 166 | **166** |
| destinations returning ≥1 gem | 90 | 88 | **88** |
| replica/real mismatches | 0 | 0 | **0** |

**Every number moves down, and that is the result.** A POI with 100 fabricated
mentions ranks as a *crowd favourite* by definition, which is why that column
falls hardest — 37 of the 87 were artefacts. Three destinations lost their
only gem, and all three were gems solely by way of a common-word core:
Colombo's "Independence Square", Ooty's "Government Museum", Prague's
"National Theatre". One destination gained: Melbourne's City Synagogue, whose
mention count fell from 61 to 2 and moved it out of the crowd band into the
gem band — the honest classification it should always have had.

⚠️ **Known cost, stated rather than buried: fame and vocabulary membership
correlate.** `guggenheim`, `griffith` and `hollywood` are real identities
travellers use bare, and they are in the vocabulary *because* they are famous,
so they are rejected too. For a hidden-**gem** feature that is close to
harmless — a POI famous enough to be a BERT token is not a hidden gem — but it
is a genuine recall loss, and the right response if it ever matters is a
curated exception list, not a lower threshold. The asymmetry that justifies
being conservative: a wrong variant *corrupts* the output, while a missing one
falls back to matching the full name.

⚠️ **Measurement caveat, recorded because it nearly became a wrong claim:**
the audit's `top_matches` holds only the top 5 POIs per destination, so a POI
disappearing from that list is not the same as its mentions going to zero. Of
42 POIs that dropped by 3+, **35 are directly measured and 7 are unknown**
(San Francisco Zoo and São Paulo Cathedral among them) — those are not quoted
as zeroes above.

**Corrects the TODO's own framing.** It cautioned that "the module is shared
with `services/poi_pinning.py`, so any change needs its own calibration pass
across both consumers". `poi_pinning.py` imports only `normalize_name`, which
is untouched here; `name_variants` and the peel guard have exactly one
production consumer, `services/gems.py`. The shared-module caution was real
about the module and wrong about the function.

24 new tests (both directions: the rejections *and* Devanagari-adjacent
transliterations like `koutoubia`, `dolmabahce`, `matangeshwar` that a
suffix-based rule would have taken with it). Suite **830 passed / 6 skipped /
0 failed**; ruff and mypy clean.

### v10.43.0 Changes (July 2026) — Input validation: nothing a user typed was bounded

A "monkey testing" pass over every field a user can type into. The starting point was that
`models/trip.py::DestinationInput.city` was a bare `str` — no length, no charset, no shape — and
**every one of these was accepted and forwarded to the Gemini prompt, Nominatim and Overpass**:
empty, whitespace-only, `🎉🎉🎉`, `A` × 10,000, embedded NUL and control characters, zero-width
spaces, an RTL override, and `Paris\nIgnore previous instructions`. `routers/itinerary.py` — the
main generation endpoint — had zero guards, and there was no `maxLength` anywhere in the frontend.

**Severity is robustness and cost, not classic injection.** SQL is ORM'd, Qdrant filters are
parameterised `MatchValue`, and prompt injection is separately fenced by `core/prompt_guard.py`
(15 tests, untouched here — the gap was user *form* input, not ingested content). What made it
worth fixing is the failure *shape*: an emoji-only destination normalised to nothing useful
downstream and produced a **fallback itinerary rather than an error**, the same
silent-plausible-wrong mode as v10.40.0's complete-but-wrong POI pool and v10.40.1's clean-looking
`0 comments ingested` run log.

**New `core/validation.py`** holds the caps, the normaliser and a set of `Annotated` field types;
`models/trip.py`, `models/chat.py`, `models/itinerary.py`, `chains/wizard_chat_chain.py` and
`chains/recommend_cities_chain.py` use them, so one change covers every route that carries a
`TripConfig`. Three decisions in it are deliberate:

| Decision | Why |
|---|---|
| **Reject, never truncate** | Silently trimming `A` × 10,000 to 80 characters produces a request that looks valid and an itinerary that looks plausible. A 422 naming the field and the actual length is the honest outcome. The single exception is the `dates` key allowlist, and it is called out in the code. |
| **Place names must contain a letter or digit** | `🎉🎉🎉` passes any length check. `str.isalnum()` is Unicode-aware, so this accepts `जयपुर`, `京都` and `Zürich` and rejects emoji-only and punctuation-only input — it is a shape rule, not a Latin allowlist. |
| **ZWJ (U+200D) and ZWNJ (U+200C) survive cleaning; every other `Cf`/`Cc` codepoint becomes a space** | Both are format characters like the zero-width space, and both are load-bearing — Devanagari conjunct control and emoji sequences. The obvious "strip all control and format characters" rule would corrupt exactly the Hindi text this India-first product most needs. **This is the fourth bug in the same family** (v10.40.4/5/6 substring false positives, v10.41.0's `\b` failing on Devanagari); the rule stated in `core/keyword_match.py` — *a character rule written for one script is an assumption about every script in the corpus* — is what caught it here. Replacement is a space rather than deletion, so a hidden separator can never fuse two tokens into one plausible word (`Paris​London` → `Paris London`, not `ParisLondon`). |

**Four real defects surfaced that the original probe had not listed:**

- 🔴 **`TripConfig.dates` was a free dict, and a long date span is a memory-exhaustion vector.**
  `chains/itinerary_chain.py::_mock_itinerary` builds one dict per day with three items each, so
  `{"start": "2026-01-01", "end": "2999-01-01"}` was ~355,000 iterations reachable from a single
  request body. Now shape-validated (ISO dates, `end >= start`, window ≤ 366 days,
  `duration_days` 1–60), **and** the loop itself is clamped — that path also runs on dicts that
  never went through the validator (eval harnesses, cached configs, its own `isinstance` fallback).
- 🔴 **Unparseable dates were swallowed and replaced with a hard-coded default.** `"01/05/2026"`
  fell into a bare `except` and became `2026-11-14`, so the user was silently planned a trip in a
  different month. Now rejected.
- 🔴 **`hops` said "multi-stop, max 5" in a comment and enforced nothing.** The frontend store caps
  at 5; the API did not. Each hop is its own cold-start ingestion — Overpass, Wikivoyage and
  embeddings — so an uncapped list is a per-request multiplier on the slowest path in the system.
- 🔴 **`routers/travel_tips.py::_tips_cache` is a process-lifetime dict keyed on the raw
  destination string.** An unbounded destination is an unbounded key, so distinct junk strings grew
  it without limit for as long as the process ran.

Also bounded: latitude/longitude (they reach a haversine calculation and an Overpass bounding box,
neither of which checked them), group sizes, budget amounts, prebooked costs, theme/persona/style
lists, chat history length, and the serialised size of the two loose dicts that get pasted into
prompts (`ChatRequest.trip_context`, `WizardChatRequest.partial_config`).

**Endpoint guards** — `geocode`, `search`, `best-time`, `travel-tips`, `reddit-highlights` and
`extract-trip` now validate through the same rules as the request bodies, via
`validate_query_param` (a `ValueError` is a 422 in a body but a 500 in a route handler, so the
conversion is explicit). `reddit-highlights`' guard sits deliberately *ahead* of its catch-all
`except`, which degrades to an empty list — inside it, a rejected input would have read as "no
highlights found".

**The 422 response body is now bounded too.** FastAPI echoes the rejected value back under
`input`, so rejecting a 100,000-character payload produced a 100,000-character error response —
the new caps would have been paid for twice. `main.py` truncates the echo to 200 characters (and
summarises long lists/dicts) while keeping the message that says what was wrong.

**Frontend**: new `apps/web/lib/limits.ts` mirrors the Python constants **exactly**, with the
reasoning recorded in it — a tighter frontend cap silently truncates something the API would have
accepted, a looser one lets the user type something that can only fail at submit. 16 inputs across
11 files now carry `maxLength`.

**Deliberately not done, and worth knowing before someone "finishes" it:** `pace`, `scope`,
`crowd_preference` and `destination_mode` are closed sets in their comments but remain bounded free
strings rather than `Literal` types. They are populated from LLM output via the wizard's
`config_patch`, and a model emitting `"Moderate"` instead of `"moderate"` would turn a cosmetic
mismatch into a hard 422 mid-flow. Tightening them needs the wizard path normalising them first.

Tests: new `tests/unit/test_input_validation.py`, **84 tests**, covering the rejection cases and —
in the same file on purpose — acceptance cases for Devanagari, CJK, Cyrillic, accented and
hyphenated names, because the tempting over-correction here is a charset allowlist that only knows
Latin. Full suite **806 passed / 6 skipped / 0 failed**; `ruff` and `mypy` clean.

### v10.42.0 Changes (July 2026) — Hidden gems: the first full-corpus audit, and the sentiment floor was the bottleneck

The first **168-destination** measurement of what `services/gems.py` actually returns. Every prior
gem audit (v10.38.2, v10.39.0) sampled 8 destinations, so there was no corpus-wide baseline. Method:
run the shipped `compute_gem_intel_sync` against the live Qdrant Cloud cluster, alongside a
diagnostic replica of its matching loop that is **cross-checked against the real function for every
destination** — the headline numbers are the real code path, never a proxy for it.

**The pool problem from v10.39.0 is genuinely fixed.** That audit's finding was that the places
travellers name were *not in the ingested pool at all* — Delhi's comments named Chandni Chowk, Red
Fort and Humayun's Tomb while the pool held 7 train stations. Post-prominence-run, Delhi matches
Chandni Chowk (5 mentions), Red Fort (2), Lotus Temple (2), Jama Masjid (1) and India Gate (1). Only
**27 of 168** destinations now fail for lack of any name match.

**🔴 The bottleneck had moved to the sentiment floor, and it was rejecting *neutral*, not negative.**
64 of the 94 zero-gem destinations failed on it alone, and 326 matched POIs across 125 destinations
were being discarded by it. Laplace smoothing puts a mention with no lexicon word in range at exactly
`(0+1)/(0+0+2) = 0.5`, just under `_GEM_MIN_SENTIMENT` of 0.55 — so "nobody used an opinion word near
this place" was indistinguishable from "this place is bad". **Measured: 75% of rejected POIs scored
exactly 0.5** (pos=0, neg=0); only 25% were genuinely negative. Red Fort, India Gate, Jama Masjid,
Elephanta Caves and Marine Drive were all discarded as neutral.

| Change | Detail |
|---|---|
| **Lexicon sized against the corpus, not taste** | The original lexicon fired on only **29%** of 1,274 real mention windows sampled from 54 destinations. Expanded with 19 positive and 6 negative additions, every one chosen from words that actually occur near a POI mention. |
| ⚠️ **The additions are counter-intuitive, and that is the point** | The corpus is YouTube comments, where most enthusiasm is aimed at the **video**, not the place — and it lands inside the same ±120-char window as the POI name. Measuring each candidate's enrichment for creator context (`video`/`vlog`/`channel`/`subscribe`; 21.8% baseline) splits them cleanly: **rejected** — `superb` 4.6x, `informative` 3.4x, `awesome` 3.0x, `helpful` 2.8x, `wonderful` 2.5x, `fantastic` 2.3x, `nice` 1.7x, `great` 1.7x; **accepted** — `clean` 0.0x, `delicious` 0.0x, `historic` 0.0x, `must` 0.3x, `good` 0.5x, `friendly` 0.5x, `love` 1.0x. `great` (97 windows) and `nice` (50) were the two largest available recall wins and are mostly praise of the vlogger; adding them would have measured production quality and reported it as place quality. Net: coverage 29% → 43% while the creator-context share of firing windows stayed flat (25% → 23%) — recall roughly doubled without importing the confound. A parametrized test asserts each rejected word scores **zero**, so a future "helpful fix" adding one breaks the build. |
| 🔴 **Cross-POI mention mis-attribution** | `build_mention_pattern` resolves longest-first within one POI's variants, but nothing did so *between* POIs. A comment reading "the grand egyptian museum" credited a mention to Cairo's **Egyptian Museum** as well as the **Grand Egyptian Museum** — two genuinely different museums, so neither can be dropped; the mention simply belongs to one of them. And the reverse: `name_variants("Lotte World Tower")` peels the structural word "tower", producing a variant identical to Seoul's real **Lotte World**, so text naming only the latter credited the former. New `_resolve_overlapping_mentions` applies two rules — longer containment wins, and an **exact name beats a derived variant at the same span** (a guess must not outrank an identity). |
| 🐛 **Identically-named POIs surfaced as two separate finds** | OSM holds Jaipur's "Pink city" (museum) and "Pink City" (attraction) as separate nodes; both normalise identically, always score identically, and both appeared in the same gem list. Now collapsed to the better-tagged one. **Only exact normalised equality is collapsed** — containment is handled by attribution instead, because containment does not imply sameness. **24 duplicate POIs across 22 destinations** were being carried. |
| **Scoring loop restructured chunk-outer** | Required for cross-POI attribution: every POI matching a given chunk must be known at once. Same total work as the old POI-outer loop — the cheap substring prefilter still gates the regex. |

**Live re-measurement across all 168 destinations** (same method, before vs after):

| | before | after |
|---|---|---|
| destinations returning ≥1 gem | 74/168 (44%) | **90/168 (54%)** |
| returning ≥1 gem or crowd favourite | 100/168 (60%) | **109/168 (65%)** |
| total gems | 127 | **172** |
| matched POIs lost to the sentiment floor | 326 | 271 |
| total matched POIs | 541 | **530** |

39 destinations gained gems and **3 lost them — those are the precision wins**: Jaipur 2→1 (the
Pink City duplicate), Porto 3→2, Vancouver 6→4. The *fall* in total matched POIs (541 → 530) is the
attribution fix removing double-counts, which is the number to watch: recall rose while
double-counting fell.

**A hypothesis stated before measuring, and refuted by it:** thin mention counts (median best-POI
count is 2) were expected to push famous landmarks into the gem list, inverting the feature's whole
premise. Only **5 of 127 gems (4%)** carried top OSM `prominence`. Real instances exist (Sagrada
Família, Kinkaku-ji) but it is not systemic. ⚠️ Honest limit: `prominence` is a tagging-completeness
proxy that under-scores famous places in sparsely-tagged cities — the project's own Humayun's Tomb
example scores 6 — so 4% is a floor, not a ceiling.

**🔴 Found, evidenced, and deliberately NOT fixed — `name_matching.py` derives demonyms.**
`name_variants("Egyptian Museum")` peels the structural word "museum" and emits the bare token
`egyptian`, which clears `_MIN_CORE_TOKEN_LEN` (8) and then matches "egyptian food", "as an
egyptian". Live: Cairo's Egyptian Museum shows **30 mentions of which 29 come from the bare token** —
the real name appears in 1 chunk. This is not a knob turn: `_MIN_CORE_TOKEN_LEN` is documented as
calibrated against the 2026-07-25 audit, `egyptian` is exactly 8 characters, and so is the genuine
recovery `immanuel` — raising it to 9 would lose the latter. The module is also shared with
`services/poi_pinning.py`, so a change there needs its own calibration pass. Filed in
`docs/NEXT_SESSION_TODO.md`.

Suite **688 passed / 6 skipped / 0 failed** (+33 in `tests/unit/test_gems.py`, 35 → 68). Ruff clean,
`mypy .` clean (171 files).

### v10.41.1 Changes (July 2026) — Prominence re-ingestion complete; a last-mile data-loss-guard gap fixed

**The re-ingestion data run started in v10.40.0 is finished: `0 of 169` destinations pending**,
verified by reading the real Qdrant Cloud cluster back (`scripts/reingest_prominence_ranking.py`),
not by trusting the run log. 160 destinations already carried a real prominence signal from prior
runs; the remaining 9 — Amalfi, Jaisalmer, Lyon, Medellin, Montreal, Nice, Oslo, Pondicherry, Siem
Reap — were re-run. Jaisalmer, Lyon, Montreal, Nice, Oslo, Pondicherry and Siem Reap all landed real
prominence data (Lyon/Montreal/Nice/Oslo at 60/60). Amalfi and Medellin exhausted their 3-attempt
budget against a persistently degraded Overpass response and were accepted on their existing stored
data, per the script's own retry rule.

**Dropped the dead `overpass.openstreetmap.fr` mirror** from `osm_overpass_fallback_mirrors`
(`core/config.py`) — it answered 403 ("white-listed usages only") to every request, so it was a
guaranteed-wasted slot in the mirror rotation during retries, worth removing before spending any
destination's final attempt on it.

**🔴 Real bug found and fixed while closing out the run: `ingest_osm_pois` (`scrapers/osm.py`)
returned `0`, not the existing stored count, when Overpass failed completely.** The function already
has two "don't overwrite good data with worse data" guards — one for a failed prominence pass with a
healthy-looking-but-unranked broad-pass result, one for a thin/dominated fetch — but the very first
check, `if not pois: return 0`, sat *before* both of them and short-circuited past them whenever
*every* mirror failed on *both* passes (a fully empty fetch, not merely a non-prominent one).
`scripts/reingest_prominence_ranking.py`'s state loader requires `record.get("osm_count")` to be
truthy before its accept-after-3-attempts rule can fire (`osm_count and (prominent or attempts >= 3)`),
so a destination hitting this path would retry **forever** rather than ever graduating — Medellin did,
three consecutive runs, all recording `osm_count=0`. Fixed by extending the existing "keep existing
data" guard to cover the fully-empty case too, returning `existing_count` instead of `0` when there is
something to preserve, consistent with the guards already just below it in the same function. No
Qdrant data was ever at risk (nothing is written on this path either way) — this was purely a
retry-bookkeeping gap.

**Resend email pipeline smoke-tested end-to-end against production for the first time.**
`POST /api/auth/password/forgot` was triggered against `https://api-production-3e3e.up.railway.app`
for a real account; Railway logs confirmed `POST https://api.resend.com/emails "HTTP/1.1 200 OK"`,
and the recipient confirmed the email arrived and the reset link completed a real password change.

### v10.41.0 Changes (July 2026) — YouTube narration: the right medium for prices, and two bugs that were hiding it

**The premise, measured first.** v10.40.4 concluded that food grounding is corpus-*density*-limited, not retrieval-limited: comments carry only 1–3 money-shaped chunks per destination because **people don't quote prices in comments**. Vloggers, however, state costs out loud, and descriptions often carry an explicit budget breakdown. That is narration — a different corpus, not more of the same one.

**New source: `scrapers/youtube_narration.py` → `youtube_narration` collection.** Wired into `core/cost_grounding.py::_price_collections()`.

| | Jaipur, live |
|---|---|
| `youtube_comments` | 149 chunks, **0** money-shaped |
| `wiki` | 10 chunks, 2 money-shaped |
| **`youtube_narration`** | **110 chunks, 24 money-shaped** |

**It costs almost nothing, by construction.** Video *discovery* makes no API call at all: the v10.40.2 comment backfill stored a `video_id` on every point, so the videos for a destination are read back out of Qdrant. The 100-calls/project/day `search.list` cap that binds every other YouTube path here is **untouched**. Transcripts need no key (`youtube_transcript_api`). Descriptions cost 1 unit per `videos.list` call and batch 50 IDs, so a full 170-destination run is ~20 units.

**Deliberately a separate collection from `youtube_comments`.** `services/gems.py` scores hidden gems by *mention count*, and that arithmetic assumes one mention ≈ one independent person. A transcript violates it — a vlogger says "Hawa Mahal" eight times in one video and it is still one voice. Merging narration into `youtube_comments` would have inflated mention counts and misclassified gems as crowd favourites. Narration reaches the price path and is deliberately kept out of gems; a test asserts both halves.

**🔴 Bug 1 — transcripts were English-only, which excluded the primary market.** `fetch_youtube_transcript` requested `languages=("en",)`. Live on Jaipur, most travel vlogs have **no English caption track**, only a Hindi auto-generated one — so an India-first product was discarding exactly the domestic narration it most needs. `languages` is now a parameter; narration passes `("en", "hi")` (English still preferred where it exists), and the itinerary-corpus path keeps its English-only default because its output feeds English few-shot prompt examples. Safe for the price path specifically because that path is **lexical**: `_scroll_price_candidates_sync` finds amounts by regex, so a Devanagari chunk containing `₹500` matches on the digits regardless of how poorly an English-centric embedding model represents the surrounding words. Effect: Jaipur narration 21 → **110 chunks**, 1 → **24** money-shaped.

**🔴 Bug 2 — `\b` silently fails on Devanagari.** Python's `\b` is defined via `\w`, and Devanagari combining vowel signs (matras) are **not** word characters — `"ा".isalnum()` is `False`. So `\bखाना\b` never matched while `\bहोटल\b` did, purely because one word ends in a matra and the other in a consonant. Measured consequence: **0 of 24** price-bearing Hindi chunks matched any food or stay keyword — every amount was discarded as topically unanchored. `core/keyword_match.py` now expresses the boundary as explicit lookarounds over "word character **or** any Devanagari codepoint", which is equivalent to `\b` for ASCII (verified: `"eat"`⊄`"great"`, `"bar"`⊄`"Barbican"`, and `go_next` still does not match a bare `go`, which `scrapers/wikivoyage.py` relies on).

This is the **third** distinct failure mode in this one keyword-matching family: v10.40.4/5/6 fixed bare-substring false *positives*; this is a false *negative* from the fix for those. Worth stating the general rule: **a boundary rule written for one script is an assumption about every script the corpus contains.**

**Hindi/Hinglish context keywords** added to `FOOD_CONTEXT_KEYWORDS` and `STAY_CONTEXT_KEYWORDS` — and, critically, to `OTHER_SPEND_KEYWORDS`. These captions are Hinglish (English transliterated into Devanagari: `रूम`, `कॉस्ट`, `पर डे`) alongside native Hindi (`खाना`, `कमरा`), so both spellings are needed. Omitting the competing-spend half would have let the two most commonly priced items in an Indian travel vlog — rickshaw fares and entry tickets — be read as meal prices. Cross-script false positives are structurally impossible (disjoint codepoint ranges), so these only add recall.

**Honest result.** Jaipur food-context matches went 0 → 2 of 24 and stay 0 → 6, but `food_per_day_estimate_inr` still returns `None` for Jaipur: two matching chunks do not yield the two in-bounds *amounts* `min_samples` requires after per-amount sentence scoping. So this is a large density gain and a real unblocking of Hindi text, **not** a claim that food grounding is now solved. `_FOOD_MEALS_PER_DAY` calibration stays deferred. The full 170-destination narration run (`scripts/ingest_youtube_narration.py`, resumable) had not been run at the time of writing — only Jaipur was ingested, as the verification case.

Suite **689 passed / 6 skipped / 0 failed**; ruff and `mypy .` clean.

### v10.40.5 / v10.40.6 Changes (July 2026) — The substring bug was in five places, not one

v10.40.4 found that price grounding matched keywords as bare substrings (FOOD's `"eat"` inside **"great"**). A sweep for the same shape found two more, both with user-visible consequences, and both older.

| Bug | Consequence |
|---|---|
| 🔴 `chains/safety.py` — `"pub"` is inside **"Public Garden"** | The kid-safety filter **silently deleted kid-friendly places from family itineraries**: Public Garden, Public Library, Public Park. `"bar"` did the same to "Bara Imambara" and "Barbican". The user never saw an error — the items simply weren't there. |
| 🔴 `core/budget_estimator.py` — `"uk"` is inside **"Sukhothai"** | `resolve_destination_tier` put a moderate-tier destination on the **premium** tier, inflating its entire budget. Any place name containing a listed code or short name was exposed. |

Both are the same failure shape as the v10.39.0 hidden-gem fix (match the token, not the blob); they simply weren't recognised as the same problem in these modules. All three now share `core/keyword_match.py`, replacing the private copy v10.40.4 had added to `core/price_extraction.py`.

**Not a blanket sweep, deliberately.** `core/budget_estimator.py`'s `PREMIUM_KEYWORDS` contains `"luxur"` — truncated *on purpose*, with a comment recording it as a past bug fix, so it catches luxury/luxurious/luxuriously. Word-boundary matching would regress that. Substring matching is correct wherever the keyword is a deliberate stem; the fix applies only where keywords are meant as whole words. The new module's docstring states that boundary so the next sweep doesn't overreach.

**Why this class of bug hides so well:** it fails as a false *positive*, on text that looks unrelated to the feature. Nothing errors, nothing logs, and the wrong outcome (a missing itinerary item, a pricier tier) looks like a plausible product decision rather than a defect. Tests here assert both directions — that "Public Garden" survives *and* that "Sky Bar" is still removed — since the tempting way to "fix" a false positive is to delete the keyword, which would quietly disable a safety feature.


**Audit completed (v10.40.6).** The remaining `keyword in text` call sites were swept individually rather than triaged by eye, and two more were real:

| Site | Bug |
|---|---|
| 🔴 `chains/wizard_chat_chain.py` | `_GENERIC_CHIP_KEYWORDS` contains `"any"`, which is inside **"Germany"**, "Tuscany", "Brittany", "Albany" — those chips were classed as generic "no preference" options and dropped from the theme-chip check. |
| 🔴 `services/poi_pinning.py` | `_interest_keywords()` yields *any* word over two characters from the user's free-text interest, so `"art"` matched **"apartment"** and `"zen"` matched **"frozen"** — falsely confirming a wiki-verified pin for an unrelated POI. |

`chains/recommend_cities_chain.py`'s preference detection was converted too (low risk, but the keywords are words).

**⚠️ One site must NOT be converted, and it is the reason a blanket sweep would have been wrong twice over.** `scrapers/wikivoyage.py`'s `SECTIONS_OF_INTEREST` is matched against section ids like `stay_safe` and `go_next` — and `_` is a *word* character to ``, so `go` does not match `go_next`. Word-boundary matching would silently stop several Wikivoyage sections from being ingested. Left as substring, with the underscore interaction now recorded.

Phrase and error-code matches (`"503"`, `"harry potter"`, `"RESOURCE_EXHAUSTED"`) were checked and correctly left alone.


Suite **670 passed / 6 skipped / 0 failed** (+10), ruff clean, mypy clean.

### v10.40.4 Changes (July 2026) — Price grounding: match the amount, not the blob

The carried-over "per-amount proximity instead of whole-snippet `context_keywords`" item. Approached as the v10.39.0 gem-matching template suggested — and it turned up the same underlying bug, in a second place.

| Change | Detail |
|---|---|
| ✅ **Context is scoped per amount, not per snippet** | `_iter_raw_amounts` now yields each amount's `(start, end)` span (valid against the source text because the symbol-pass masking is equal-length), and `_amount_has_context` asks whether *that amount* is on-topic. Sentence-first; widened to ±90 chars only when the amount's own sentence names nothing bought; and never widened when that sentence names a **competing** kind of spending (new `OTHER_SPEND_KEYWORDS` — transport, entry fees, rentals). |
| ⚠️ **Strict sentence scoping was tried first and measured as too strict** | It correctly rejects "Metro ticket €2. Dinner was lovely." but *also* rejects "We ate at a bistro. It was €25", where the amount's sentence is topically silent. Live, that drove `food_per_day_estimate_inr` to `None` on all 8 destinations spot-checked — precision bought by switching the feature off. Hence the widen-unless-competing rule. |
| 🔴 **Pre-existing bug: keyword matching was bare substring** | `FOOD_CONTEXT_KEYWORDS` contains `"eat"`, and `"eat" in "great"` is `True` — so any snippet saying "great views" counted as food context. Now word-boundary anchored via a cached per-set pattern. **Exactly the v10.39.0 failure shape** (match the token, not the blob), in a module nobody had connected to it. That also made `"ate"`, `"bistro"`, `"diner"` safe to add, having been unusable as substrings (`ate` ⊂ `plate`/`private`/`climate`). |
| ✅ **Stay grounding accepts a single mention (`_STAY_MIN_SAMPLES = 1`)** | Stricter extraction pushed thin-but-real destinations back onto the flat default — Paris and Jaipur each retain exactly one genuine stay mention. Stay tolerates the lower bar better than food: its amounts are already per-night, so there is no meals/day factor to multiply a lone sample's error by. **The trade is deliberate: for such destinations one number now sets the stay line, and stay has no floor — bounds are the only guard.** |

**Live A/B against the real corpus** (read-only; "old" simulated by neutralising the per-amount check, so both arms see identical retrieved snippets):

| | old n → new n | old median → new |
|---|---|---|
| Paris food | 2 → 1 | ₹1,108 → ₹1,800 |
| Paris stay | 2 → 1 | ₹1,702 → ₹2,988 |
| Kyoto stay | 11 → 10 | ₹10,000 → ₹13,300 |

With `_STAY_MIN_SAMPLES=1`, stay grounding is **restored for Paris (₹2,988) and Jaipur (₹1,200)** with Goa/Kyoto/Colombo unchanged.

**🔴 The finding that matters most, and it corrects an assumption made earlier the same day: a complete corpus is not a dense one.** Completing the YouTube backfill (v10.40.2, 170/170 destinations) was expected to unblock the `_FOOD_MEALS_PER_DAY` calibration. It does not. Across 8 destinations there are only **0–3 extractable food amounts each**, and `food_per_day_estimate_inr` returns `None` for all of them — *before and after* this change, since `min_samples=2` is not met either way. **Food grounding is corpus-density-limited, not retrieval- or filter-limited.** Calibrating the meals/day multiplier from this data would be picking a number again, which is precisely what the original deferral existed to prevent. The item stays deferred, now with a measurement behind it rather than an assumption.

**Also fixed:** `tests/unit/test_airbnb_stay_estimate.py`'s stay stub didn't accept the new `min_samples` kwarg, and `_grounded_or_flat` wraps that call in `except Exception` — so the stale signature surfaced as a silent fall-back to flat rather than a `TypeError`. Same shape as the v10.38.3 test-isolation lesson: **a broad except around a mocked call turns stub drift into a passing-looking wrong answer.**

Suite **660 passed / 6 skipped / 0 failed**, ruff clean, mypy clean.

### v10.40.3 Changes (July 2026) — YouTube quota discipline: quota errors are terminal, and scripts get the app's redaction

Cleanup of the two things v10.40.1 deliberately deferred, plus a correction to a claim v10.40.1 introduced.

| Change | Detail |
|---|---|
| ✅ **A quota refusal is terminal, not transient** | `search_travel_videos` retried *every* exception three times with 5s/10s backoff, so a 429 cost **3 calls against a 100/day cap and could not succeed on any of them** — the mechanism behind 141 wasted calls on 2026-07-26, and the uniform ~19s-per-destination cadence in that run log was the doomed backoff sleeping. 403/429 now return immediately. `fetch_video_comments` already applied exactly this rule to 403; the search path simply never had the matching branch. A 500 or dropped connection is still retried, and both behaviours are covered by tests. |
| ✅ **Standalone scripts get the app's redaction** | New `core/logging_config.py::configure_script_logging()` installs `RedactionFilter` on a plain-text console handler and pins `httpx` to WARNING. **All 12 scripts under `scripts/` now use it instead of bare `logging.basicConfig`.** The previous mitigation (silencing httpx in one script) addressed one instance; this closes the class. It also *replaces* any handler `basicConfig` already installed — otherwise the record would still reach an unfiltered one. |
| ✅ **Stop logging the exception that carries the key** | `raise_for_status()` embeds the full request URL — key included — in its message, and both YouTube fetch paths interpolated the caught exception into their warnings. They now log `type(e).__name__`. This is the actual source of the leak; redaction is the safety net, not the fix. |
| 🔴 **Found while fixing: the key could reach a file, where no filter runs** | `scripts/ingest_youtube_full.py` wrote `f"{type(e).__name__}: {e}"` into its resumable **JSONL state file**. A logging filter only covers records passing through a handler, so a secret bound for disk bypasses it entirely. `core/logging_config.py` now exposes a public `redact()` for non-log sinks and the script uses it. (2026-07-26's failures were Qdrant timeouts, so nothing actually leaked by this path.) |
| ⚠️ **Correction to v10.40.1: the cold-start gate does *not* over-subscribe the cap** | That entry claimed the gate's 5 ingestions/hour ≈ 120/day exceeds the 100/day `search.list` cap on its own. It does not — every cold start routes through `search_travel_videos`, which consults the budget window *first*, so a single process is hard-bounded at the budget per rolling 24h however many cold starts fire. `services/destination_ingestion.py`'s own comment already said as much. |

**What the real quota gap is, and why it is not being closed yet.** The budget window is **per-process**; the quota is **per-project**. Prod, a manual script and an eval run each keep their own in-memory window and can collectively exceed 100/day — which is what happened in miniature on 2026-07-26 between a diagnostic probe and the backfill script. Closing it properly means a shared, persisted counter: a DB write on every `search.list` call. Deliberately not built, because the first change in this release makes the failure cheap and visible — a process meeting an exhausted quota spends one call per destination instead of three, logs at WARNING, and leaves the work pending for a later run. Worth revisiting only if that stops holding.

### v10.40.2 Changes (July 2026) — YouTube corpus complete; mypy runs for the first time and finds three real bugs

Two carried-over items closed. Suite **646 passed / 6 skipped / 0 failed** (full tree, unit + integration), `ruff check .` clean, and **`mypy .` now reports `Success: no issues found in 166 source files`** — from 91 errors.

**1. ✅ The YouTube comment corpus is complete: 170/170 destinations.** The 90 outstanding destinations went through in one pass on a fresh Pacific quota day, plus a retry for stragglers: 90 ingested, **13,477 comments**. Verified against the real cluster rather than the run log — `youtube_comments` holds **25,347 points across 172 destinations**, up from 12,429 / 84.

**Worth recording: 8 of the 90 failed on the first pass with Qdrant `read/write operation timed out`, not quota** — and all 8 succeeded on an immediate retry, so they were transient cluster blips. The initial hypothesis was contention with the concurrently-running prominence re-ingestion; that was wrong, since failures continued at a similar rate after that job was paused. The v10.40.1 resume fix is what made this recoverable: the run reported `remaining: 8` and left them pending, where the old code would have recorded all 8 as done and abandoned them. **Each failure still costs a `search.list` call** (the search succeeds, only the Qdrant write fails), which against a 100/day cap is the real reason the resume semantics matter.

**2. ✅ CI's mypy step: the crawl abort is fixed, and the 91 errors behind it are cleared.**

The recorded cause was `apps/api/eval/` missing an `__init__.py`, with a note that both candidate fixes change import resolution for the eval harness and so need the eval scripts re-run. **That is true of adding `__init__.py`, but not of the alternative**: `explicit_package_bases` is a mypy-only setting with no runtime effect whatsoever, so the entry points and their `sys.path` manipulation are untouched. Set in `pyproject.toml` rather than the CI command so local and CI agree; `.github/workflows` is unchanged. The missing `__init__.py` was also **not specific to `eval/`** — `scripts/` has the same shape, and excluding `eval/` merely moved the abort there. Also excluded `venv/`, which CI never sees but a local run was type-checking.

With the crawl fixed, mypy type-checked 166 files for the first time. **Three were real bugs:**

| Bug | Detail |
|---|---|
| 🔴 `services/destination_ingestion.py` — a cancelled ingestion read as a *success* | The cold-start gather narrowed on `isinstance(result, Exception)`, but `gather(return_exceptions=True)` also returns `CancelledError`, which inherits `BaseException`, **not** `Exception`. A cancelled source fell through to the else branch, appended the exception object itself to `counts`, and then read as truthy — i.e. as a non-zero ingestion count, so `if not osm_count and not wiki_count` treated the destination as populated. |
| 🔴 `services/comparison.py` — one missing LLM key killed the whole comparison | `winner=row.get("winner")` passes `None` into `ComparisonParameter.winner`, which is `str = ""` and non-optional, so any row the LLM returned without a `winner` key raised a pydantic `ValidationError` — taking out the entire qualitative comparison, not just that row. |
| 🔴 `services/comparison.py` — guaranteed `AttributeError` | `trip_config.dates.duration_days` is attribute access on a plain `dict`. `TripConfig.dates` is declared `dict` and its documented shape is `{"start", "end", "flexible"}`; `duration_days` is a key the wizard may add, so this is now `.get("duration_days")`. |

**Everything else was a false positive, fixed by making the invariant explicit rather than suppressing it.** No blanket `# type: ignore` was added; the three that exist carry a specific error code and a one-line reason (two stdlib/third-party stub gaps — `sys.stdout.reconfigure`, slowapi's handler signature — and one test helper mimicking `httpx.HTTPStatusError`). Highlights: the two `expires_at < now` checks in `routers/auth.py` were safe only via `or` short-circuiting, which mypy cannot correlate across two variables, and now share an `_as_utc()` helper that also removes a duplicated naive-datetime block; `RefreshToken.__table__.update()` became `update(RefreshToken)`, the modern properly-typed API; `set_cookie`'s options are a `TypedDict`, with `cookie_samesite` narrowed at the call site rather than tightened in config, where making pydantic reject anything outside the literal set would turn a today-working value like `"None"` into a refuses-to-boot error. `user.email` is genuinely nullable (a Google-SSO account can carry only `google_sub`), so the password-reset path now checks it.

**Two smaller latent bugs also fell out of the harness code:** `scripts/_regen_budget_anchors.py` indexed `estimate_bare_minimum_budget()`'s result without a `None` check (it returns `None` when it cannot estimate, e.g. unknown group size — a `TypeError` mid-run), and `eval/run_budget_comparison.py` fed `None` totals from failed extractions straight into `coefficient_of_variation`, which now drops them rather than counting them.

**Generalisable:** 55 of the 91 errors came from **five `dict[str, object]` inference sites** — a mixed-value dict literal that is then `**`-splatted into typed parameters emits one error *per candidate parameter type*, so the error count wildly overstates the work. Two annotations alone cleared 32. Judge this kind of backlog by distinct sites (54), not by error count.

### v10.40.1 Changes (July 2026) — The YouTube backfill meters against the wrong quota, and the resume state hid it

Taken up as "finish the YouTube backfill — 90 destinations left". The run failed on **every one of the 47 destinations it reached**, and did so while logging `0 comments ingested` for each: no exception, no failure count, a clean-looking run log. Paris, London, New York and Mumbai returning zero travel-vlog comments is what gave it away.

| Change | Detail |
|---|---|
| 🔴 **The binding quota is not the one the code models** | `search.list` has its own dedicated cap — `defaultSearchListPerDayPerProject`, **100 calls per project per day** — which is a *separate meter* from the 10,000 units/day the code and comments reason about. `core/config.py`'s note that "80 searches ≈ 8,000 units … leaves real headroom" is measuring the non-binding quota: against the one that actually stops you, 80 of 100 is 80% with no headroom at all. Confirmed from the live 429 body (`quota_metric: youtube.googleapis.com/search_list`, `quota_limit_value: 100`), alongside `videos.list` and `i18nLanguages.list` returning 200 — the key and project were fine; only search was capped. **`youtube_daily_search_budget` is now 100, matching the cap**: holding back 20 was reserving headroom this window cannot actually protect, since a concurrent prod cold-start spends from the same project quota and never consults it. The budget is now a "don't exceed the provider" bound; graceful degradation comes from the retryable-no-op handling, not from the margin. |
| 🔴 **The resume state recorded failures as completed work** | `_load_done()` keyed every recorded row as done regardless of outcome, so all 47 zero-comment rows would have been skipped on every future run — the destinations would have been silently abandoned, not retried. This directly contradicts the rule the module docstring describes and the scheduler follows (leave `youtube_last_ingested_at` NULL so an empty result is a *retryable no-op*, never a recorded-but-empty success). **Fixed**: a destination counts as done only if comments were actually ingested, with a 3-attempt cap so a genuinely un-vlogged place can't spend a search call on every run forever — the same idiom `scripts/reingest_prominence_ranking.py::_load_state` already used. The summary's `remaining` now re-reads state under that same rule instead of counting every attempted row as finished. |
| ⚠️ **Quota errors are retried three times (found, not fixed)** | `scrapers/youtube_comments.py::search_travel_videos` retries every exception 3× with 5s/10s backoff. `fetch_video_comments` deliberately special-cases 403 as "not transient, don't burn retries"; search has no equivalent case, so a 429 costs **3 calls instead of 1** and cannot succeed on any of them. That is 141 wasted calls across the 47 destinations, and the 5s+10s of doomed sleeping is the uniform ~19s-per-destination cadence in the run log. |
| ⚠️ **The budget window gives no cross-run protection (unchanged, by design)** | `_search_times` is a process-global deque, so every fresh invocation of the script starts believing the full budget is available. That is correct for the long-lived API process it was written for, and wrong for a script run repeatedly by hand. |
| ⚠️ **Quota accounting is per-process, not per-project** | *(Corrected in v10.40.3: an earlier version of this row claimed the cold-start gate's 5/hour ≈ 120/day exceeds the cap on its own. It does not — every cold start routes through `search_travel_videos`, which consults the budget window first, so one process is hard-bounded at the budget per rolling 24h.)* The real gap is that prod, a manual script and an eval run each keep their own in-memory window, and together they can exceed the project's 100/day. |
| ⚠️ **The API key reaches standalone logs (found, not fixed)** | `raise_for_status()` embeds the full request URL — including `key=AIza…` — in its exception message, and the scraper logs that message. **Production is unaffected**: `core/logging_config.py`'s `RedactionFilter` rewrites `AIza…` before the formatter. But scripts using `logging.basicConfig` bypass the filter, so the key was written 47 times into a local run log. The mitigation recorded against this in the previous session (silencing `httpx` to WARNING) does not cover this path — it is the scraper's own warning, not httpx's. |

**Quota-day arithmetic, since it is easy to get wrong twice.** These quotas reset at **midnight Pacific**, not UTC and not local. The first backfill ran 2026-07-25 08:13 UTC, which is 01:13 **PDT on 2026-07-25**; the retry was attempted 2026-07-26 03:49 UTC, which is still 20:49 **PDT on 2026-07-25** — the *same* quota day, roughly 20 hours later by the wall clock and zero days later by the meter. The 80 calls from the first run were still on the books.

**Verification.** The new resume rule was checked against the real state file (80 done / 90 pending, unchanged) and across every branch — ingested, failed-then-succeeded, empty-twice, errored, and exhausted-after-3-attempts. The 47 bogus rows were stripped from `scripts/out/ingest_youtube_full_state.jsonl` (backed up first, and only after asserting every retained row carried a non-zero count). Nothing had been written to Qdrant, so no data was lost or corrupted — the failure was entirely upstream of ingestion. `ruff check` passes.

### v10.40.0 Changes (July 2026) — The POI pool: famous landmarks were unreachable, not out-ranked

Taken up as v10.39.0's top follow-up, "rank the OSM POI pool by prominence". Ranking was needed, but it was the *second* of two causes, and on its own it would have changed nothing for the worst destinations — the landmarks were not losing a competition for the 60 slots, they were never candidates.

| Change | Detail |
|---|---|
| 🔴 **The Overpass query only ever asked for `node` elements** | Famous sites are mapped as *areas*. A live probe settled it: Kiyomizu-dera, Kinkaku-ji and Ginkaku-ji are `way` elements and Delhi's Jama Masjid a `relation`, so a `node[...]` query could never return them however the results were ranked. Small neighbourhood shrines and cafés — which *are* nodes — held the slots by default. The tell was in the code already: `_build_overpass_query` asked for `out center` and the parser read `element["center"]`, both of which only mean anything for ways/relations. Only the query kind was missing. |
| ⚠️ **Why the one-line fix (`node` → `nwr`) does not work** | Overpass's `out <limit>` truncates in element-type order, **nodes first**. So a capped `nwr` query returns an all-node result and silently drops every way and relation — live-verified: an `nwr` query for Kyoto capped at 3000 came back 3000/3000 nodes. It would have looked like a working fix. Removing the cap instead is the other extreme: an uncapped all-ways query times out on public Overpass in any dense city (Kyoto 504'd on all three mirrors). |
| ✅ **A second, prominence-filtered pass** | Nodes + ways + relations, restricted to elements carrying `wikidata`, over a wider 15km radius, with **no result cap** (a cap would reintroduce the nodes-first truncation above). The `wikidata` filter is what makes an uncapped query affordable: Delhi returns 159 elements, Kyoto 345, Bangkok 668 — not tens of thousands. Merged ahead of the existing broad node pass, which is unchanged. |
| **`wikidata` alone, measured — not a regex over `wikidata\|wikipedia\|heritage`** | The wider filter was tried on the same cities and is not worth it: Istanbul gained 7 elements out of 836 for double the query time (42s → 89s), and Bangkok's wider query **timed out on every mirror after 202s** where the `wikidata` one succeeded in 36s. Nearly everything tagged `wikipedia` or `heritage` carries `wikidata` too. |
| ✅ **Prominence scoring** | A plain weighted tag count — `wikidata`/`wikipedia` 3 each, `heritage` 2 (+2 more for `heritage=1`, OSM's convention for world/UNESCO listing), `website` 1, `name:en` 1. Deliberately not learned or LLM-derived: it runs over every element of every ingestion with no API budget, and it only has to beat *arrival order*, which is what it replaces. It measures how well-documented a place is — the part OSM can tell us for free — not how good a visit would be. |
| ✅ **Selection by prominence tier, not by category equality** | The existing round-robin gave **a cinema exactly the same claim on a slot as the Red Fort**: with the prominence pass merged in but round-robin unchanged, Delhi's 60 came back with 4 cinemas and 4 art galleries but only 4 attractions, and Red Fort/Humayun's Tomb/Qutub Minar/India Gate still missed out. Selection now runs in descending prominence tiers, round-robinning across categories *within* each tier. Across tiers prominence wins; within a tier no category can crowd out the others; and when nothing carries a prominence signal the pool collapses to a single tier — byte-identical to the previous behaviour. |
| ✅ **Per-category hard cap (settles a question left open since v10.37.0)** | Tiers alone don't bound the tail — a monument-dense city has dozens of *equally* prominent monuments that would take every slot before a museum got one. A category is now capped at 25% of the pool, half the data-completeness gate's `MAX_CATEGORY_SHARE=0.5` so pools clear that gate with margin rather than sitting on the line. POIs past the cap are deferred behind everything else, not discarded, so a thinly-mapped destination still fills its quota. This is the "per-category hard cap in `osm.py`" option the Paris-metro/temple-town skew decision was parked on. |
| 🔴 **New data-loss guard: a failed prominence pass must not overwrite good data** | Hit live on the first run — Delhi's prominence query 403'd on all three mirrors, and the broad-pass-only fallback returned a full 60 well-distributed POIs containing **none** of Red Fort, Humayun's Tomb, Qutub Minar, India Gate, Lotus Temple, Jama Masjid or Lodhi Gardens. Every existing health check passed it. The prominence pass's success is now tracked explicitly (it cannot be inferred from the POIs) and a failed pass will not overwrite an already-populated destination. A destination with nothing stored still ingests — degraded data beats none — and an *empty* prominence result is treated as success, since a rural destination genuinely may have no `wikidata`-tagged POI. |

**The tuning was measured, not guessed.** Raw Overpass results for Delhi, Kyoto and Bangkok were cached once and eight scoring/selection variants compared on identical inputs, scored as "how many of this city's genuinely famous landmarks — the ones the v10.39.0 audit found travellers naming — end up in the final 60, out of those actually present in the raw data":

| Variant | Landmarks retained |
|---|---|
| **shipped** (weights above, cap 0.25) | **25/37** |
| cap 0.35 / cap 0.20 / heritage 3+3 | 25/37 |
| area bonus + nearest-centre tie-break | 25/37 |
| area bonus alone (+1 or +2) | 24/37 |
| nearest-centre tie-break alone | 24/37 |

Two ideas worth recording as *rejected on evidence*, since both sound obviously right:
- **Scoring areas above nodes** (a traced way/relation is "more significant" than a point) is *worse* on its own — Delhi drops 10/14 → 9/14, losing Chandni Chowk to traced buildings.
- **Relaxing the category cap to 0.35** looked like a win on two cities (Kyoto 10→11) and evaporated at three. Not worth weakening the diversity bound for.

No variant beat the shipped one, so it stays — it is also the simplest and the only one with an independent justification (half the completeness gate's threshold).

**Live results** (re-ingestion in progress at time of writing; verified by reading payloads back off the cluster, not from the run log): Kyoto's pool went from 21 obscure temples + 20 small museums to Kiyomizu-dera, Kinkaku-ji, Ginkakuji, Ryōan-ji, Nijō Castle and Katsura Imperial Villa, 60/60 carrying a prominence signal, top category share 0.35 → 0.25. Delhi gained Red Fort, India Gate, Jama Masjid, Lotus Temple, Chandni Chowk, Purana Qila, Hauz Khas and Jantar Mantar (attractions 4 → 14, cinemas 4 → 1). Bangkok gained Wat Arun, Grand Palace, Chatuchak and Jim Thompson House. **Tokyo — which failed all three v10.39.0 re-ingestion attempts and was still 58/60 Japanese-script — went through on the first try at 60/60 Latin-script, 60/60 prominent, share 0.10**, closing that carried-over item. **Hidden gems moved for the first time on these destinations: Kyoto 0 → 3 (Byōdō-in, Kinkaku-ji, Murin-an), Goa 0 → 1 (Museum of Goa), and Delhi now correctly classifies Chandni Chowk as a crowd favourite** — the exact POI the v10.39.0 audit found commenters naming 4× while the pool lacked it.

**What the category cap does *not* fix.** It defers over-cap POIs rather than discarding them (so a thin destination still fills its 60), which means a destination without enough *other* categories still ends up dominated. Alleppey re-ingested at **0.63 top-category share, 38 of 60 places of worship** — which is genuinely what OSM has there. So v10.40.0 removes the *artificial* skew (Paris metro, Bangkok/Delhi train stations) but not the real kind; whether to accept temple/backwater-town skew or relax the completeness gate for it remains a product call.

**Known residual, and it is OSM's data, not the ranking:** Delhi's Humayun's Tomb carries only `wikidata` + a *Hindi* `wikipedia` tag — no `heritage`, no `name:en`, no `website` — so it scores 6, while the Sulabh International Museum of Toilets (fully tagged, `wikipedia:en`, website) scores 8. Delhi's OSM data barely uses `heritage` at all, so its scores bunch at 6 and ties break on arrival order. Kyoto, where `heritage=1` is used properly, ranks perfectly: Kinkaku-ji, Kiyomizu-dera, Ryōan-ji, Nijō Castle and Byōdō-in all score 12 and lead the pool. The signal that would fix Delhi is Wikidata sitelink count (how many language editions describe a place), which needs a second API and is a bigger change than this one.

### v10.39.0 Changes (July 2026) — Hidden gems: name matching, and the ingestion bug that made it moot for 17 destinations

Picked up as "gem-intel name matching under-fires" (the open item from v10.38.2). A read-only audit of the live corpus first — 8 destinations, real `osm_pois` + `youtube_comments` — because the premise deserved checking before tuning anything. **It did not survive the check.** Normalisation and aliasing recovered roughly **one POI per destination**, and the aggressive part of it recovered as many false matches as real ones. Three other causes were doing the actual damage.

| Change | Detail |
|---|---|
| 🔴 **OSM POI names were being stored in the local language** | `scrapers/osm.py` read `tags.get("name")`, which OSM defines as the name *in the local language*. So Kyoto's POIs went into the cluster as 清水寺 and Cairo's in Arabic. Everything downstream treats a POI name as text an English-speaking traveller would recognise — gems searches for it in comments, `poi_pinning` matches it against LLM-proposed names, **and the itinerary renders it to the user**. Live audit across all 170 ingested destinations: **17 had ≥10% of names in a non-Latin script, 9 of them above 66%** — Tokyo 58/60, Taipei 56/60, Seoul 56/60, Athens 54/60, Tbilisi 53/60, Osaka 53/60, Cairo 50/60, Kyoto 49/60, Bangkok 40/60. Now prefers `name:en`, then `int_name`, then a Latin fragment parenthesised inside an otherwise non-Latin name (`新熊野神社 (Imakumano Shrine)`), keeping the original in a new `name_local` payload field. A live Overpass probe confirmed the data is there to use: `name:en` on 43 of 107 named Kyoto nodes. |
| 🔴 **Gem candidates were dominated by transport nodes** | Istanbul's entire live gem list was Kadıköy, Karaköy and Beyoğlu — three metro stops. Jaipur's second-strongest match was a POI literally named "Railway Station"; Khajuraho's strongest was a station called "Khajuraho". `services/gems.py` now excludes `train station`/`airport` POI types from both lists (they are ingested deliberately, for route anchoring — they are just not somewhere to send a traveller as a find), and excludes any POI whose name is the destination itself. |
| **New `services/name_matching.py`** | `normalize_name()` + `name_variants()` + `build_mention_pattern()`, shared with `services/poi_pinning.py`, which had its own half of the same logic. Variants cover what OSM actually does: a comma-appended locality (`Marine Drive, Kochi`), a trailing structural word (`Matangeshwar Temple` → `matangeshwar`), a parenthesised translation. Matching is word-boundary-anchored so a short derived core can't match inside a longer word. |
| **The variant rules are calibrated against the corpus, not guessed** | Aggressive core-name stripping produced `Central Park` → `central`, `Moti Park` → `moti`, `The village` → `village` — all live false positives. The distinctiveness guard (a *derived* single-token variant must be 8+ characters) is exactly where the audit's real recoveries — `immanuel`, `sitaramji`, `matangeshwar` — separate from those. Every one of those strings is a test case in `tests/unit/test_name_matching.py`. |
| 🐛 **Diacritic folding silently deleted letters NFKD can't decompose** | Turkish dotless `ı` has no combining decomposition, so "decompose, drop combining marks" turned **Kadıköy into "kad koy"**, which matches nothing. Same for `ø ł đ ß æ œ þ`. Now explicitly folded. **This bug was live in `poi_pinning`'s normaliser too**, so interest-pinning had the same blind spot. |
| 🐛 **Apostrophes were split rather than removed** | `St Mary's` normalised to `st mary s`, matching neither `St Marys` nor `St Mary's` as typed. Also `poi_pinning`, where it was being papered over by the fuzzy-ratio fallback. |
| 🐛 **Sentiment scoring missed lexicon words next to punctuation** | `_sentiment_around` hand-replaced `,`, `.` and `!` before splitting, so `a real gem;` or `(peaceful)` scored zero. It now runs on already-normalised text, where every punctuation mark is a separator. |

**Live result on unchanged data** (read-only, real cluster): Kochi 0 → 1 gem (Marine Drive), Khajuraho's train-station "gem" replaced by a real one (Matangeshwar Temple), Jaipur's "Railway Station" noise gone with Hawa Mahal retained, Istanbul's three metro stops correctly gone to zero.

**The next bottleneck is the POI pool, not the matcher.** Delhi, Goa and Bengaluru still return zero with 100–200 comments each, and the reason is now measured rather than assumed: the places travellers actually name are **not in the ingested 60-POI pool at all**. Delhi's comments name Chandni Chowk (4×), Agrasen ki Baoli (4×), Red Fort, Humayun's Tomb, Connaught Place — none present, while 7 train stations are. Goa's name Fontainhas and Anjuna — neither present, while 24 of its 60 POIs are places of worship. `_prioritize_landmarks` round-robins across categories to stop any one dominating, but nothing in the pipeline ranks by *prominence*, so the cap fills with whatever Overpass returned first. Filed as the top follow-up.

Suite **585 passed / 6 skipped / 0 failed** (+16). Ruff clean.

### v10.38.3 Changes (July 2026) — Transactional email actually works in production for the first time

`RESEND_API_KEY` had never been set on Railway, so every password-reset and admin-notification email in production took the "no key" branch: no send, and the raw reset link written to the Railway logs. Now configured end to end against a real verified domain.

| Change | Detail |
|---|---|
| **Sending domain** | `wanderplanner.org` registered and verified with Resend — DKIM (`resend._domainkey`), return-path `MX` + SPF (`send`), and DMARC (`_dmarc`) live at the registrar, all four confirmed by direct DNS query against both a public resolver and the authoritative nameserver before verifying. `*.vercel.app` cannot be used for this: Resend requires DNS records the subdomain's owner can't add. |
| **Prod config** | `RESEND_API_KEY` + `EMAIL_FROM_ADDRESS=Wanderplanner <no-reply@wanderplanner.org>` set on Railway. |
| 🐛 **The default from-address was a domain nobody owns** | `core/config.py` defaulted to `no-reply@wanderplanner.app`, so even with a key present every send would have 403'd on an unverified domain. Default and `.env.example` now point at the real verified domain, with a comment explaining the constraint. |
| **Stale comment removed in `core/email.py`** | It claimed the no-key branch "is never reached in prod since RESEND_API_KEY is always configured there." The key was never configured there, so that branch *was* the production path — quietly writing live reset links into logs. Replaced with a note on what actually enforces prod config (the `core/config.py` guard, not a comment). |
| **Log redaction covers Resend keys** | `_APIKEY_RE` matched `AIza…`/`sk-…`/`gsk_…` but not `re_…`. Added, and the whole filter now has direct test coverage (`tests/unit/test_logging_redaction.py`) — including the live case of httpx logging a YouTube URL with the key in the query string. |
| 🐛 **A "unit" test was silently hitting the live Qdrant Cloud cluster** | `test_budget_estimator.py`'s autouse fixture stubbed `community_median_price_inr` but not `community_food_per_day_inr` — v10.38.0 split food onto a second entry point and the fixture was never updated, so food grounding reached the real cluster on every run. It stayed green only because the corpus was empty; the 11,838-comment YouTube backfill gave Colombo genuine food signal and `test_stay_and_food_fall_back_to_flat_tier_when_corpus_empty` began failing. Now both entry points are stubbed — the file runs in 0.12s instead of 18.8s, which is the real tell that it had been doing network I/O all along. |

Suite **576 passed / 6 skipped / 0 failed**. Ruff clean.

### v10.38.2 Changes (July 2026) — The production guards were never running in production; first full YouTube backfill

A prod-env audit (prompted by "is `YOUTUBE_API_KEY` set?") turned up two live misconfigurations and one dead safety net. All three are fixed.

| Change | Detail |
|---|---|
| 🔴 **`is_production()` — the v10.26 cookie guard was inert on Railway** | Both prod validators in `core/config.py` gated on `os.getenv("ENVIRONMENT", "development") != "production"`. **Railway never sets a bare `ENVIRONMENT`** — it injects `RAILWAY_ENVIRONMENT_NAME` / `RAILWAY_ENVIRONMENT`. So the `COOKIE_SAMESITE` validator *and* the `JWT_SECRET` validator have returned early on every production boot since they were written. Prod is correct today only because `COOKIE_SAMESITE=none` happens to be set by hand; deleting or mistyping it would have silently reinstated the cross-site session-drop bug the guard exists to prevent. New `is_production()` helper recognises all three vars and is used by both validators. |
| **Why the tests didn't catch it** | Every test in `test_config_validation.py` did `monkeypatch.setenv("ENVIRONMENT", "production")` first — they proved the guard works *when told it is production*, and nothing asserted that the real deployment ever tells it that. Added 6 tests: `Settings()` with no cookie config under `RAILWAY_ENVIRONMENT_NAME=production` must raise; a Railway *staging* env must **not** be held to prod rules; default `JWT_SECRET` rejected under Railway-production; plus an autouse fixture clearing all three markers so a developer running under `railway run` gets CI's results. |
| **Prod env fixes (applied live)** | `YOUTUBE_API_KEY` was absent → set. 🔴 `NOMINATIM_USER_AGENT` was still `wanderplan/1.0` — the 2026-07-21 Wikimedia-403 fix only ever reached `.env`/`.env.example`/the code default, and **a Railway variable overrides the code default**, so prod had been sending the policy-violating UA (shared with Nominatim/Overpass) the whole time. Now `WanderPlannerBot/1.0 (https://github.com/kunalsmathur-gif/wanderplanner)`. |
| **New: `scripts/ingest_youtube_full.py`** | One-time backfill neither automatic caller could have done: the cold-start gate only fires on a first-ever request, and `_refresh_youtube_comments` uses an `IntervalTrigger` with no `start_date`, so its first fire is 14 days after boot. Scheduler-identical ordering (NULL-first, then `request_count` DESC), resumable JSONL state, stops cleanly on the rolling search budget. **Result: 80/80 destinations, 11,838 comments, 0 failures**, verified against the live cluster (`youtube_comments` 12,429 points / 84 destinations). Stopped exactly on budget with 90 destinations left for a follow-up run. |
| **Verified: the API key is not leaked to logs** | httpx logs full request URLs at INFO and YouTube passes the key as a query param, so this was checked rather than assumed: `logging_config.RedactionFilter`'s `AIza…` pattern rewrites it to `[redacted-key]` before the formatter runs. Standalone scripts using `logging.basicConfig` get no such filter, so the new script sets `httpx` to WARNING. |

**Live spot-check of the v10.38.0 gems dead-zone fix, now that real data exists:** `compute_gem_intel_sync("Jaipur")` returns Hawa Mahal (9 mentions, sentiment 0.67, source YouTube) — the exact POI that fell into the old 7–11 dead zone and returned empty. **Still open:** most destinations return 0 gems (Kyoto, Kochi, Khajuraho all 0 with 150–240 comments each). The matcher requires an OSM POI *name* to appear literally in comment text, which under-fires wherever locals/vloggers use a different name than OSM records — and where it does fire it can surface thin signal (Istanbul's only gem is "Kadıköy", a train station, at 2 mentions). Name-normalisation/aliasing is the next step for this feature.

### v10.38.1 Changes (July 2026) — Repo-wide Ruff cleanup: backend is lint-clean under the version CI actually runs

CI runs a bare `ruff check .` on `apps/api`, but the tree carried **318 pre-existing violations** at `be9e30e`, so that step had been failing on every run reaching it. Cleared in one dedicated pass. Three of the violations were latent bugs, not style noise — the value of the pass is mostly in those.

| Change | Detail |
|---|---|
| **Ruff config modernised** | `select`/`ignore` moved from the deprecated top-level `[tool.ruff]` into `[tool.ruff.lint]` (`apps/api/pyproject.toml`). Ruff had been emitting a deprecation warning on every invocation. Added a `tests/**` → `E402` per-file-ignore: test modules deliberately group imports under section banners next to the tests that use them, which reads better than one hoisted block. |
| **Version pin** | `ruff==0.4.9` was already pinned in `requirements-dev.txt` and matches the local venv, so CI and local now agree exactly. No pin change was needed — the drift was in the config, not the version. |
| 🐛 **Two module docstrings were silently dead** | `scrapers/wikivoyage.py` and `services/comparison.py` placed their docstring *after* `from __future__ import annotations`, which makes it an ordinary string expression, not a docstring — both modules had `__doc__ = None`, and every subsequent import was flagged `E402`. Docstring moved to line 1 in both. |
| 🐛 **`F821` undefined name in `chains/itinerary_chain.py`** | `_parse_expense_breakdown` annotated its return as the string `"ExpenseBreakdown"` and re-imported the symbol inside the function body — but `models.itinerary` is already imported at module level, so the local import was redundant and the forward-ref unresolvable to any type checker. `ExpenseBreakdown` hoisted into the existing module-level import; annotation is now a real reference. |
| 🐛 **`F841` dead local in `chains/feasibility_chain.py`** | `_mock_feasibility` read `trip_summary["destination"]` into `dest` and never used it — the mock ignores the destination entirely. Removed. |
| **Mechanical fixes (304 auto + 13 unsafe-auto)** | `I001` import sorting (98), `UP017` `timezone.utc` → `datetime.UTC` (65, safe on the `python:3.11-slim` runtime), `UP007` `Optional[X]` → `X \| Y` (36, including the runtime `response_model=` on `GET /admin/requests/me`), `F401` unused imports (16), `UP031` percent-format → `str.format` in the `scripts/reingest_*.py` logging calls (6), plus assorted `UP038`/`UP037`/`F541`/`E401`/`F811`. |
| **Verified** | `ruff check .` → *All checks passed*. Full backend suite **563 passed / 6 skipped / 0 failed**. |

**Known-unrelated CI gap (not introduced here, not fixed here):** the `mypy . --ignore-missing-imports` step fails before type-checking with `eval\config_loader.py: Source file found twice under different module names` — `apps/api/eval/` has no `__init__.py`. Confirmed identical against a pristine `be9e30e` worktree. Fixing it means either adding `apps/api/eval/__init__.py` or switching the step to `--explicit-package-bases`; both change import resolution for the eval harness, so it wants its own change.

### v10.38.0 Changes (July 2026) — YouTube ingestion automated behind a quota budget, gems classification dead zone, price-retrieval category error, food grounding anchored on observed daily data

Four carried-over `NEXT_SESSION_TODO` items, all previously deferred as "needs more data before tuning is defensible". Two of them (gems thresholds, `_FOOD_MEALS_PER_DAY`) were deliberately fixed **structurally** rather than by picking new constants — tuning a magic number without calibration data just relocates the guess. Three of the four turned out to have a real bug behind the stated symptom.

| Change | Detail |
|---|---|
| **NEW** rolling-24h YouTube search budget (`scrapers/youtube_comments.py::_search_budget_available`) | The prerequisite for automating YouTube ingestion at all, not incidental hardening: `search.list` costs 100 of the free tier's 10,000 daily units, while the cold-start gate permits 5 ingestions/hour ≈ 120/day ≈ 12,000 units — wiring ingestion in naively would have exhausted the daily quota and starved manual/eval runs. Process-global sliding window, same shape as `destination_ingestion.py`'s existing cold-start cap; `settings.youtube_daily_search_budget = 80` (≈8,000 units, leaving headroom for `commentThreads.list` at 1 unit/call). Over budget degrades to "no videos found", which every caller already handles. `search_travel_videos()` also gained `query`/`max_results` overrides. |
| **NEW** YouTube ingestion wired into the cold-start gate (`services/destination_ingestion.py`) | Previously manual-only, deliberately, to avoid unmetered quota spend. Now runs on a destination's first request, gated on `youtube_ingest_on_cold_start` (opt-out, default on) **and** a key being configured. `youtube_last_ingested_at` is left NULL whenever ingestion was skipped or returned 0 (over budget, no videos, comments disabled), so the destination stays retryable rather than being recorded as freshly-ingested-but-empty. |
| **NEW** scheduler job `_refresh_youtube_comments` (`core/scheduler.py`) | Kept separate from `_refresh_osm_pois` because the economics differ — OSM/Wikivoyage are free and unmetered, this spends quota. Own cadence (`youtube_refresh_days = 14`), per-run cap (`youtube_refresh_batch_size = 20`), and **NULL-first then demand-ranked** (`request_count` DESC) so a limited quota is spent on the destinations users actually ask for. Timestamp is written only on a non-zero ingest. New column + migration `0005_youtube_ingestion_state` (applied and verified locally). |
| **FIXED** cold-start ingestion discarded successful work on a sibling source's failure (`services/destination_ingestion.py`) | Found while adding YouTube as a third source. The `asyncio.gather` had no `return_exceptions`, so a raising Overpass fetch threw away an already-completed Wikivoyage scrape (and vice versa). Each source is now independent, with per-source failure logging. |
| **NEW** live YouTube itinerary-video discovery (`scrapers/itinerary_corpus.py::discover_youtube_itinerary_videos`) | Replaces the intentionally-empty static `YOUTUBE_ITINERARY_VIDEO_IDS` seed list. Reuses `search_travel_videos()` (shared client + quota budget) with an **itinerary-shaped** query, deliberately distinct from the hidden-gems phrasing the comments path uses, over a new India-weighted `YOUTUBE_ITINERARY_SEED_DESTINATIONS` (10 India / 6 international — correcting the pattern where every prior seed list under-served domestic destinations). Results are filtered through the existing `_is_itinerary_shaped()`, since `search.list` relevance happily returns "10 THINGS TO KNOW" videos with no day structure for the extraction chain. The manual list is retained as a keyless supplement and deduped against. |
| **FIXED** hidden-gem classification dead zone (`services/gems.py`) | Not a tuning problem — a bug. The fixed pair (gem ≤ 6 mentions, crowd ≥ 12) left POIs mentioned **7–11 times matching neither branch**, silently absent from both lists; this is precisely what happened to Jaipur's only match (Hawa Mahal, 8 mentions), which is why `compute_gem_intel_sync` returned empty despite real signal existing. Absolute counts also can't be correct for two corpus sizes simultaneously — 8 mentions means "obscure" in a 500-comment corpus and "most-discussed place here" in a 30-comment one. Replaced with a **per-destination percentile split** (`_crowd_mention_threshold()`, top ~20%), clamped into `[_CROWD_MIN_MENTIONS = 3, _CROWD_ABSOLUTE_MENTIONS = 12]` and falling back to the absolute ceiling below `_MIN_POIS_FOR_RELATIVE_SPLIT = 5` mentioned POIs (a percentile over 1–2 POIs would make a lone 5-mention POI "the crowd"). The branches now **partition** every mentioned POI; the sentiment floor is the only remaining reason one appears in neither list, which is intended. Being scale-free, it stays correct as ingestion coverage grows instead of needing a per-destination re-tune. |
| **FIXED** price-grounding retrieval — a category error plus two silent bugs (`core/cost_grounding.py`, `core/price_extraction.py`) | Presence of a price is a **lexical** property, but snippet selection was **semantic**: a casual "Choki dani 700 per person" comment is topically about a restaurant, not about "cost", so it carries almost no signal for a price-flavoured query and never reached the top-N. New `_scroll_price_candidates_sync()` does a bounded destination-filtered scroll (400 chunks/collection) keeping chunks that literally contain a price, via the same regex the extractor uses (new `has_price_mention()`); merged ahead of the semantic pass in new `community_price_samples()`, kept separate from `community_price_snippets()` so the prompt-hint callers' token budget is unaffected. **Silent bug 1:** snippets were head-truncated at 280 chars, so a chunk whose only amount sat past that point was passed on with the amount already removed — it looked on-topic and contributed nothing, invisibly; the prompt path now uses `price_focused_excerpt()` (window centred on the amount, keeping the trailing "per person"/"per night" qualifier in view). **Silent bug 2:** the extraction path must not truncate at all — only a regex reads it, and an excerpt discards additional prices later in the same chunk (Wikivoyage "Eat"/"Sleep" sections routinely list several); it now passes full chunk text. |
| **CHANGED** food grounding anchored on directly-observed daily data; floor is now conditional (`core/price_extraction.py::food_per_day_estimate_inr`, `core/budget_estimator.py::_grounded_food_per_day`) | `_FOOD_MEALS_PER_DAY = 3.0` was flagged as an uncalibrated default with a permanent floor compensating for it. Rather than invent a calibration number, the multiplier was demoted to a **fallback**: the new extractor returns `(value, directly_observed)` — when enough amounts are already expressed per-day ("we spent ₹900 a day on food") they're used directly with **no multiplier involved at all**; otherwise per-meal amounts are scaled and pooled. The safety floor now applies **only to the reconciled path**, because its entire justification ("the meals/day factor is uncalibrated, so a low result may be an artefact") does not apply to a directly-observed daily figure — which is exactly the "anchored against real daily-spend data" condition the floor was always meant to be temporary pending. Directly-observed figures are therefore trusted in both directions (the same latitude stay grounding already had). Net effect: the uncalibrated constant becomes progressively less load-bearing as ingestion coverage improves, instead of requiring a one-off calibration pass to retire. `_grounded_or_flat()` lost its now-superseded `floor`/`per_day_meal_multiplier` params (stay-only). |
| **Live verification** (read-only, real Qdrant Cloud cluster) | Price-bearing snippets surfaced vs. the semantic-only path: Jaipur **0→1**, Paris **0→3**, London **1→3**. Dropping the extraction-path truncation took Paris from 1→2 extractable amounts, crossing `min_samples` and producing **the first non-None food grounding this feature has ever returned** (₹3,375/day). That figure is partly contaminated by a €5 *bus fare* from a chunk that mentions food words elsewhere (snippet-level context matching is coarse) — the floor correctly discarded it (3,375 < flat 6,546 → `food_community_based=False`), which is the floor doing its job. **Grounding still returns None for most destinations, but the cause has shifted from retrieval to corpus density**: destinations yield 0–2 extractable on-topic amounts against `min_samples=2`. Per-amount proximity matching (rather than whole-snippet) is the next highest-value step. |
| **Tests** | Full unit suite green: **529 passed, 6 skipped, 0 failed** (+54 tests, from 475). New files `tests/unit/test_cost_grounding_retrieval.py` (12) and `tests/unit/test_scheduler_youtube_refresh.py` (8). Note: the repo is **not** ruff-clean under the currently-installed ruff (257 pre-existing errors at HEAD, mostly `UP017`/`UP007`/`I001`; sibling migrations 0003/0004 carry the same `I001`) — this session's files match surrounding style rather than diverging, but CI runs a bare `ruff check .`, so a dedicated `--fix` pass plus a ruff version pin is worth scheduling. |

### v10.37.0 Changes (July 2026) — 3 count-invisible wrong-city geocode fixes + final backlog re-ingestion, and the food per-meal→per-day reconciliation ("item A" proper fix)

Two threads: (1) closing the destination-data backlog — a full live re-audit showed only 10/168 destinations failing the completeness gate (none wiki/osm-zero anymore), and spot-checking the *passing* set surfaced 3 destinations silently holding data for the wrong same-named city (the gate checks POI *count*, never *correctness*); (2) the deferred proper fix for the v10.35 food-grounding floor — reconciling per-meal Wikivoyage prices to a per-day budget so grounding can legitimately fire again.

| Change | Detail |
|---|---|
| **FIXED** 3 silently mis-geocoded destinations (`services/geocode.py::GEOCODE_QUERY_OVERRIDES`) | Caught by geocode-spot-checking the *passing* completeness set (reverse-geocoded country vs. the catalog's regional grouping in `scrapers/reddit.py`), which the count-only gate cannot detect. **Austin** resolved to Austin, Nevada (a ~150-person former mining town, 3 OSM POIs) not Austin, Texas — this was *also* its gate failure. **La Paz** resolved to La Paz, Mexico (Baja California Sur) not the Bolivian seat of government (catalog groups it with Santiago/Montevideo/Cusco); passed the gate with 60 POIs for the wrong city. **Valencia** resolved to Valencia, Venezuela not Valencia, Spain (grouped with Seville/Granada/Nice/Lyon); also passed with 60 wrong-city POIs. All three are same-name collisions the generic Wikipedia country cross-check can't resolve (Austin is a same-country namesake; La Paz/Valencia are comparably prominent to the intended city), i.e. the override escape hatch's exact purpose. 4 new tests (`test_geocode.py::TestGeocodeQueryOverrides`, incl. a lowercase-key guard). |
| **Data** final straggler re-ingestion (`scripts/reingest_geocode_fixes_and_stragglers.py`, new) | Re-ingested the 10 gate-failures + the 2 count-invisible wrong-city ones. The 3 geocode-fixed destinations have their wrong-city data **wiped first** (`delete_stale_destination_points(..., keep_ids=set())`) so the `ingest_osm_pois()` data-loss guard can't fall back to it on a transient thin fetch. After one spaced-out retry pass for Overpass mirror-saturation noise (504/429/403): **7/12 pass** — Austin (60, Texas), La Paz (60), Valencia (60), Sri Lanka (62%→27%), Pushkar (63%→32%), Varkala (62%→28%), Lonavala (thin→20). The **5 residual are genuine real-world category skew, not bugs**: Paris (train-station 58% — metro density, the documented "no per-category cap" limitation), Dharamshala/Alleppey/Mahabaleshwar (place-of-worship 53–78%, temple/backwater towns), Khajuraho (restaurant 71% — tiny temple town whose OSM is genuinely mostly eateries). The structural fix (per-category hard cap in `scrapers/osm.py`) stays deferred pending eval data on itinerary-quality impact. |
| **FIXED** food-grounding per-meal→per-day reconciliation (`core/price_extraction.py`, the v10.35 floor's proper follow-up) | `extract_price_mentions_inr`/`median_price_inr` gained a `per_day_meal_multiplier`, threaded through `cost_grounding.community_median_price_inr` → `budget_estimator._grounded_or_flat`; the food call site passes new `_FOOD_MEALS_PER_DAY = 3.0`. It's **unit-aware** — a new `_iter_raw_amounts()` tags each extracted amount as per-day (e.g. "₹1500 per day") vs per-meal/unspecified (the dominant Wikivoyage "Eat" case) and scales only the latter, so already-daily mentions aren't double-counted. Snippet masking switched single-space→equal-length so the trailing-unit check reads correct offsets (existing extraction results unchanged — all prior `test_price_extraction.py` cases still green). Bounds now apply to the *reconciled* per-day value (a ₹50 snack ×3 = ₹150 kept; a ₹4000 "dish" ×3 = ₹12000 dropped). **The food floor is kept** as a safety net (the meals/day factor is a principled default, not calibrated), so grounding can still only *raise* food above the flat bare-minimum; the win is that a genuinely food-expensive destination's real per-day figure can now clear the flat and flip `food_community_based=True` (before, a single meal's price almost never did). |
| **Tests / housekeeping** | Full unit suite green: **475 passed, 6 skipped, 0 failed**; +~20 tests. Note corrected: `tests/unit/test_budget_estimator.py` is **not** uncollectable on the current Python (3.12 venv) — it collects and runs (12 pass); the long-standing "always `--ignore`, Python-3.9 collection error" caveat is stale for this environment. Its `community_median_price_inr` mock had silently gone stale (missing the v10.35-era `context_keywords` kwarg) because nobody was running it — signature fixed. |

### v10.36.0 Changes (July 2026) — Generic geocode + Wikivoyage disambiguation pipelines, OSM data-loss guard, 21-straggler backlog fully closed

Replaced the growing pattern of one-off per-destination overrides with two reusable disambiguation pipelines, per explicit direction to make these fixes generic ("if city name not found, search hub towns, check alternative spellings, check whether its a country, etc.") so future real-time destination fetches and RAG enrichment benefit automatically, not just the batch-ingestion scripts.

| Change | Detail |
|---|---|
| **Rewrote** `services/geocode.py` around a generic disambiguation pipeline | New: `_needs_second_opinion()` (triggers on low Nominatim importance, small-settlement types, or no genuine `class=place` hit at all — the last condition added after Patagonia's hits were all `class=boundary`); `_wikipedia_disambiguate()` (cross-checks the top Nominatim hit's country against the same-name Wikipedia article's country — catches wrong-country collisions like Cappadocia resolving to an Italian village, importance 0.52 vs the correct Turkish region's 0.16, so raw importance-ranking alone would've picked wrong); `_hub_town_in_bbox()` (Overpass hub-town lookup for country/region-sized hits, e.g. Ladakh/Maldives-class names, bbox-guarded at 6° after an unguarded Tokyo-sized bbox reliably 504'd Overpass). Old `GEOCODE_QUERY_OVERRIDES` kept only as a fast-path escape hatch for genuinely irresolvable same-name ties (e.g. Cartagena, Colombia vs Spain — both real/prominent, no heuristic picks the travel-intended one). 14 new tests (`tests/unit/test_geocode.py`). |
| **Rewrote** `scrapers/wikivoyage.py` around a generic Wikivoyage disambiguation pipeline | New: `_wikivoyage_search_title()` (404 fallback via Wikivoyage's own search API — fixed Washington DC/Rio de Janeiro, which 404'd on Python `.title()` mis-casing); `_resolve_disambiguation()` (detects genuine disambiguation pages via the MediaWiki `pageprops.disambiguation` signal, then picks the right same-name candidate by cross-referencing the destination's geocoded country, with a `_REGION_QUALIFIERS` tie-break for same-country region-vs-city ties like "Oaxaca (state)" vs "Oaxaca (city)"). Both checks fire only when the initial scrape yields zero docs, to avoid extra network calls on ordinary (non-ambiguous) ingestions. 4 new test classes (`tests/unit/test_wikivoyage_scraper.py`). |
| **FIXED** OSM data-loss regression in `ingest_osm_pois()` | The existing delete-then-upsert only guarded against a fully-empty fetch; a non-empty-but-severely-thin result (Overpass silently returning 1 truncated POI without raising) overwrote a previously-good 60-POI dataset for Las Vegas and Tulum. New `core/qdrant.py::count_destination_points()` + a guard that skips the overwrite (keeping existing data) when a still-thin-after-retry result is smaller than what's already stored. 2 new tests + updated mocks in 4 existing ones. |
| **Data** all 21 remaining stragglers from the prior 95-destination batch now pass the completeness gate | Cappadocia (wrong-country geocode, now 60 OSM POIs); Queenstown/Washington DC/Oaxaca/Cartagena/Rio de Janeiro (`wiki_chunk_count=0`, fixed via the Wikivoyage pipeline); Las Vegas/Tulum (data-loss regression, restored to 60 POIs each — also caught latent wrong-country geocodes for both, corrected to US/Mexico); Kolkata/Cancun/São Paulo/Bora Bora (OSM restaurant-share >50%) root-caused as stale data predating an earlier session's round-robin balancing fix — plain re-ingestion cleared all 4 (also caught a latent Bora Bora→Indonesia geocode bug, corrected to French Polynesia). |
| **Tests** | Full backend suite green: 451 passed, 6 skipped (same pre-existing unrelated `test_budget_estimator.py` Python-3.9 collection error, always `--ignore`d). +20 tests this session. |

### v10.35.0 Changes (July 2026) — Batch: SSRF DNS-rebinding fix, food-grounding floor, India seed-list expansion, eval-anchor regen, 23-destination re-ingestion + first live data-completeness run

A multi-item maintenance batch (`docs/NEXT_SESSION_TODO.md` items 1/3/4/9/10/11). One code-quality regression was found *and* fixed within the same session (the food-grounding floor, below).

| Change | Detail |
|---|---|
| **FIXED** DNS-rebinding (TOCTOU) gap in the SSRF-hardened URL fetch (`chains/extract_trip_chain.py`) | The 2026-07-20 SSRF fix resolved+validated the host but let httpx **re-resolve** DNS independently at connect time — an attacker controlling a low-TTL domain could swap in a private/metadata IP in that window. Now `_assert_public_host()` returns the exact validated `(host, pinned_ip)`, and a new `_pinned_get()` connects to that literal IP (`httpx.URL.copy_with(host=ip)`) while preserving TLS SNI + certificate verification against the real hostname (httpcore `sni_hostname` request extension) and the `Host` header. Closes the residual gap flagged in the 2026-07-20 security pass. 22 new tests (`tests/unit/test_ssrf_ip_pinning.py`); live-verified (real HTTPS fetch works, `127.0.0.1` blocked). |
| **FIXED** food-grounding under-estimation (found via item 9 after re-ingestion activated it) | `core/budget_estimator.py::_grounded_or_flat()` gained a `floor` param; the food call site passes `floor=True`, so a community-grounded food figure *below* the flat `_COST_MATRIX` bare-minimum is discarded in favour of the flat value (reported honestly as `food_community_based=False`). Wikivoyage "Eat" prices are per-dish/per-meal and were undercutting a full day's food budget (e.g. Venice food ₹1,190/day vs a realistic ₹6,546) once the re-ingestion below gave those destinations extractable Eat prices. Grounding can still *raise* food above flat; stay keeps no floor (a below-flat stay can legitimately be a cheap destination). Mirrors `feasibility_chain.py`'s `max(llm, floor)`. 4 new tests. |
| **Data** 23 zero-data international destinations re-ingested (live production Qdrant writes) | Via `scripts/reingest_pilot_batch.py` (batch list injected, script unchanged): Bangkok, Istanbul, Prague, Venice, Santorini, Phuket, Maldives, Abu Dhabi, Oslo, Reykjavik, Warsaw, Mexico City, Vancouver, Quito, etc. 14 fully populated (60 OSM POIs + wiki); 22/23 now have wiki data. Residual: 8 still OSM-zero (city-level = transient Overpass rate-limits worth a longer-backoff retry; region/country-level = geocoding-area issue), and Bangkok wiki=0 (hub-article gotcha). |
| **Data/eval** India seed-list expansion (`scrapers/reddit.py`, `scrapers/itinerary_corpus.py`) | `KNOWN_DESTINATIONS` 134→168 (+35 India tier-2/3 towns, hill stations, heritage & beach circuits) so organically-mentioned domestic destinations stop being bucketed as `"general"`; `WIKIVOYAGE_ITINERARY_TITLES` +2 live-verified India itineraries ("Kerala Backwaters", "Rail travel in India"), India coverage 1→3. Pure data (no quota, no auto-spend). |
| **Eval** budget-comparison golden anchors regenerated (`eval/budget_comparison_dataset.json`) | Re-ran the estimator against all 5 BC cases; regenerating **all five** (not just the two originally flagged) caught BC-002 had also drifted. New totals: BC-002 ₹534,100 (was ₹323,600), BC-004 ₹69,000 (was ₹51,100), BC-005 ₹503,800 (was ₹293,300); BC-001/003 unchanged. All flat-based (no grounding fired → deterministic). `docs/eval-set.md` §10C-pre caveats resolved. |
| **Eval** first live data-completeness check run (`eval/run_data_completeness_check.py`) | Against the real cluster: **5/16 golden destinations pass (31%)**. Most eval-golden cities (Tokyo, Kyoto, Rome, Barcelona, Singapore, LA, Edinburgh…) have wiki=0 or category-skewed OSM from pre-fix ingestion — concrete confirmation the published fidelity numbers were measured against degraded data, and a priority re-ingestion list. |
| **Tests** | Full backend suite green: 426 passed, 6 skipped (same pre-existing unrelated `test_budget_estimator.py` Python-3.9 collection error, always `--ignore`d). +26 tests this session (22 SSRF + 4 food-floor). |

### v10.34.0 Changes (July 2026) — Decision: ToS-restricted pricing sources allowed pre-commercial, tracked for removal at launch

Reverses part of v10.32.0's licensing-driven source swap. The user weighed in: this project is not yet in a commercial phase (no paid product, no revenue), so sources whose ToS only restrict *commercial* reuse (Numbeo, budgetyourtrip.com) are fine to use now — they don't need to be avoided pre-emptively, just tracked so they get removed/re-sourced before any commercial launch.

| Change | Detail |
|---|---|
| **Reverted** `stay_per_night_pp` (moderate/premium mid_range) to direct budgetyourtrip.com figures | `core/budget_estimator.py::_COST_MATRIX` — moderate/mid_range ₹7,916 → ₹7,968, premium/mid_range ₹29,049 → ₹29,050 (the v10.32.0 Wikivoyage-multiplier reconstruction, kept in the docstring as a documented compliant fallback for whenever budgetyourtrip.com needs to be dropped again — the two land within ~1 INR of each other). `core/airbnb_pricing.py`'s discount-ratio comments updated to match the new denominators (0.262→0.260 Bangkok, 0.339 Paris unchanged; `_AIRBNB_STAY_DISCOUNT_MULTIPLIER` itself unchanged at 0.30). |
| **Kept** premium-tier `food_per_day_pp` Numbeo-sourced, unchanged | ₹4,245/₹6,546/₹9,300 — no numeric change, since these were already Numbeo-sourced and are now explicitly allowed pre-commercial rather than needing replacement. |
| **Added** explicit "PRE-COMMERCIAL-ONLY DATA SOURCES" flag | New module-level docstring section in `core/budget_estimator.py` naming both sources (Numbeo, budgetyourtrip.com), why they're currently allowed, and that they must be removed/re-sourced before commercial launch. Mirrored in `docs/NEXT_SESSION_TODO.md` as a standing pre-launch checklist item. |
| **Research done, not applied**: tested whether a single Wikivoyage→Numbeo multiplier generalizes across cities | Live-compared Wikivoyage "Eat" section listings (which use their own Budget/Mid-range/Splurge categorization) against fresh Numbeo data for Paris, Bangkok, and Tokyo. Paris alone gave a consistent ~1.12x multiplier, but Bangkok's ratios came out 2.37x/1.53x/1.30x by spending style (Wikivoyage's Bangkok "Budget" tier is genuine street-food/night-market pricing — a different real category than Numbeo's "inexpensive restaurant" line item, despite sharing a label), and Tokyo/Shinjuku's Wikivoyage listings were too sparse/format-inconsistent (single dish vs. all-you-can-eat buffet vs. no price listed at all) to compute a ratio at all. Separately confirmed Numbeo has zero coverage for smaller destinations (live-checked Rishikesh: "Cannot find city id") where Wikivoyage has at least some real listing data — the two sources' reliability trades off in opposite directions depending on destination tier. Conclusion: no single global multiplier is defensible; a per-city multiplier (same caution already applied to the stay-pricing Wikivoyage multiplier) would be the correct approach if Numbeo is ever dropped, not a blanket conversion factor. Full math in `core/budget_estimator.py`'s docstring. |
| **Tests** | No test changes needed beyond the reverted constants (all existing tests parametrize off `_COST_MATRIX` rather than hardcoding values). Full backend suite green (400 passed, 6 skipped, same pre-existing unrelated `test_budget_estimator.py` Python 3.9 collection error). |

### v10.33.0 Changes (July 2026) — Cold-start ingestion rate limit + itinerary-corpus RSS feed expansion (scaling-tech-challenges §8 item 5 + NEXT_SESSION_TODO item 3)

Follow-up session closing out 4 low-effort, dependency-clean hygiene items flagged in `docs/NEXT_SESSION_TODO.md`. Two of the four (the `prompt_guard` unit test and the `FieldCondition` payload-index audit) turned out to already be complete from a prior same-day session (`cabb20a`) — the TODO doc just hadn't been updated to reflect it; corrected here rather than duplicating the work.

| Change | Detail |
|---|---|
| **Built** Cold-start rate limit on demand-driven destination ingestion (`scaling-tech-challenges.md` §8 item 5) | `services/destination_ingestion.py::_cold_start_budget_available()` — a process-global sliding-window cap (`_MAX_COLD_STARTS_PER_HOUR = 5`) checked right before `ensure_destination_ingested()` does its expensive first-time work (geocode + Overpass + Wikivoyage + embeddings). When exhausted, the request is skipped (not persisted, so it's retryable once the window clears) and logged at WARNING. Scoped **process-global rather than per-IP/session**, a deliberate narrowing of the original design: no caller identity reaches this function today (`chains/itinerary_chain.py` calls it with just a destination string) — true per-IP scoping would need request-context plumbing through that call chain, a bigger change deferred until real abuse data shows it's needed. 4 new unit tests in `tests/unit/test_destination_ingestion.py` (cap enforcement, window expiry, exhausted-budget skip behavior). |
| **Expanded** `TRAVEL_BLOG_FEEDS` in `scrapers/itinerary_corpus.py` (item 3's free hidden-gems source list) | Added Two Wandering Soles and Y Travel Blog, both live-verified (real, full-body-fetchable RSS feeds). Two Wandering Soles had the best itinerary/gem-title hit rate of everything spot-checked this session (e.g. "Portugal's Best Hidden Gem", "The 2-day Kyoto Itinerary I'd Recommend" — 3 of 12 recent items); Y Travel Blog next-best ("Queensland's Best Kept Secret"). Not yet ingested against the real Qdrant cluster. |
| **Confirmed already done** `tests/unit/test_prompt_guard.py` (28 tests) and the `FieldCondition` payload-index audit | Both were completed in commit `cabb20a` the same day as v10.32.0 but `docs/NEXT_SESSION_TODO.md` still listed them as outstanding — doc corrected to match reality rather than re-doing the work. |
| **Tests** | 4 new tests (destination-ingestion rate limit) plus the pre-existing 28 (`prompt_guard`). Full backend suite green (434 passed, 6 skipped — same pre-existing unrelated `test_budget_estimator.py` Python 3.9 collection error, always excluded via `--ignore`). |

### v10.32.0 Changes (July 2026) — ⚠️ Commercial-licensing fix: budgetyourtrip.com → Wikivoyage + Inside Airbnb, plus new Airbnb-based stay-estimate feature

Follow-up session auditing v10.31.0's newly-merged pricing sources for commercial-use licensing compliance, prompted by the user flagging budgetyourtrip.com's ToS. **Both of the two commercial pricing sources merged in v10.31.0 and the prior 2026-07-21 session turned out to have licensing problems**: budgetyourtrip.com's ToS prohibits commercial use outright, and Numbeo's ToS (used for v10.31.0's premium-tier food figures) requires a paid "Data License" for anything beyond personal/academic use. This session fixes the `stay_per_night_pp` half of that problem; **the Numbeo-sourced premium food figures remain unfixed and are the top priority for next session** (see `docs/NEXT_SESSION_TODO.md`'s top section).

| Change | Detail |
|---|---|
| **Fixed** `_COST_MATRIX['moderate']['mid_range']`/`['premium']['mid_range']` `stay_per_night_pp` re-sourced off budgetyourtrip.com | Replaced with real Wikivoyage (CC BY-SA 3.0 — already the license basis for the `wiki` RAG collection) per-listing hotel prices, scraped from district "Sleep" sections via raw wikitext fetches (`curl .../action=raw`, not the lossy rendered-page fetch tool, which silently drops or reorders Sleep sections on large articles) — technique and city-specific gotchas (large "hub" articles like Bangkok/Paris/Tokyo have no inline pricing; it lives in per-district sub-articles, some of which are `#REDIRECT` stubs) documented inline in `_COST_MATRIX`'s docstring. Wikivoyage's own nominal listing prices are **much lower** than budgetyourtrip's self-reported "average traveller spend" figures — a real methodology gap, not just a source swap — so the same dollar figures were reconstructed via an empirically-derived multiplier: moderate tier 3.08x (avg of independently-confirmed Bangkok 3.10x / Athens 3.06x), premium tier 4.31x (Paris-only, flagged as needing a second anchor). Net numeric change is small (moderate mid_range ₹7,968→₹7,916; premium mid_range ₹29,050→₹29,049) — this fix is about provenance, not the number. Applied via `scripts/recalibrate_pricing.py`. |
| **New** Inside Airbnb (CC BY 4.0) wired in for two specific, narrow cases — not the default hotel source | (1) User explicitly requests an Airbnb/vacation-rental stay: new `wants_airbnb_stay()` keyword detector (`"airbnb"`, `"air bnb"`, `"air b&b"`, `"vacation rental"`, `"self-catering"`, `"self catering"`) applies a new `_AIRBNB_STAY_DISCOUNT_MULTIPLIER = 0.30` (derived from Bangkok 0.262x / Paris 0.339x Inside-Airbnb-vs-Wikivoyage ratios) on top of the normal hotel figure. (2) Wikivoyage has no usable inline hotel pricing for a destination — confirmed real case: Istanbul — falls back to new `core/airbnb_pricing.py`'s seeded `airbnb_hotel_equivalent_pp_inr()` lookup (currently only `"istanbul": 10757`, computed from a live Inside Airbnb CSV + live FX rate), inserted as a new rung in `estimate_bare_minimum_budget()`'s fallback chain between community-RAG-grounding and the flat `_COST_MATRIX` default. New `scripts/ingest_airbnb_pricing.py` automates computing further seed entries from any Inside-Airbnb-covered city (~100 cities globally, mostly Europe/Americas/some Asia-Pacific; confirmed zero India coverage). Both paths compose correctly — an explicit Airbnb request on a fallback city applies the discount to the real Airbnb-derived rate, not double-discounted (live-verified for Istanbul). `estimate_bare_minimum_budget()`'s return dict gained `stay_airbnb_based`/`stay_airbnb_fallback_used` flags; `budget_estimate_prompt_hint()`'s assumption-text logic updated with an `elif` chain prioritizing whichever applies. |
| **Still open** Numbeo-sourced premium food figures (`food_per_day_pp`: economical ₹4,245 / mid_range ₹6,546 / premium ₹9,300, from v10.31.0) | Same commercial-licensing problem as budgetyourtrip.com, not yet remediated this session — flagged to the user mid-session, not yet resolved. Needs the same treatment as the stay-pricing fix above (a compliant substitute source + either a reconstruction multiplier or a fresh recalibration). Top priority for next session per `docs/NEXT_SESSION_TODO.md`. |
| **Found, not yet acted on** `docs/eval-set.md` §10's BC-004/BC-005 golden `anchor_low_inr`/`anchor_high_inr` values are now stale | Spot-checked by recomputing `estimate_bare_minimum_budget()` against the exact stored trip configs: BC-004 (Mumbai→Bangkok) now computes ₹68,800 vs. the stored ₹51,100 anchor; BC-005 (Mumbai→Paris) now computes ₹503,800 vs. the stored ₹293,300 anchor — drift accumulated across this session's stay-pricing fix and the v10.31.0 food recalibration before it, not a new bug. Regenerating the dataset's golden values is an eval/data decision left for next session, not folded into this doc-only pass. |
| **Tests** | 14 new tests in `tests/unit/test_airbnb_stay_estimate.py` (kept in its own file, separate from the pre-existing broken `test_budget_estimator.py` — an unrelated Python 3.9 `X \| None` collection-time error, always excluded via `--ignore`). Full backend suite green (430 passed, 6 skipped). Live-verified end-to-end for Bangkok/Paris/Istanbul/Istanbul+explicit-Airbnb-request/Colombo (no Airbnb seed data — falls through to the flat default cleanly). Committed as `b65e3cd`. |

### v10.31.0 Changes (July 2026) — Budget-estimator premium-tier recalibration + new LLM-vs-estimator budget comparison eval + Moonshot/Kimi eval provider (item 5/10)

Follow-up session continuing item 10's budget-estimator recalibration (`core/budget_estimator.py`'s `_COST_MATRIX`, last touched partially in v10.28.0), plus a new eval comparing WanderPlanner's own estimator against asking a general-purpose chatbot directly. **Update (v10.32.0):** these changes were subsequently committed, but the Numbeo cost-of-living source used for the food-figure recalibration below was found to require a paid commercial data license for non-personal use — the `stay_per_night_pp` fix (also flagged there for a different source, budgetyourtrip.com) was remediated in v10.32.0; **the Numbeo food figures below are still unremediated**, see v10.32.0 for the current status.

| Change | Detail |
|---|---|
| **Recalibrated** `_COST_MATRIX['premium']` food figures | Sourced real Numbeo cost-of-living data for Paris (raw HTML fetch, since Numbeo's JS-rendered page returns nothing via markdown fetch) — all 3 spending styles independently sourced (not one anchor + proportional scaling like v10.28.0's flight-band fixes): economical ₹2,000→4,245, mid_range ₹3,800→6,546, premium ₹6,500→9,300 — a 1.4–2.2x undershoot, worse at lower spending styles (same shape as the earlier Sri Lanka food fix). Spot-checked `moderate`-tier food figures against real Bangkok Numbeo data too and found them already close (~3% off) — left unchanged, verified-not-broken. `stay_per_night_pp` for both tiers is **still not recalibrated** — Numbeo doesn't track hotel rates, and Booking.com/Skyscanner are both JS-rendered and can't be scraped by this repo's fetch tooling, same blocker noted in v10.28.0. Full sourcing math documented inline in `_COST_MATRIX`'s docstring for future auditability (FX rates used: EUR/INR ≈ 93, THB/INR ≈ 2.42, both derived from ~1.08 USD/EUR and ~36 THB/USD). |
| **Built** `eval/run_budget_comparison.py` + `eval/budget_comparison_scoring.py` + `eval/budget_comparison_dataset.json` | New eval trio (docs/eval-set.md §10) comparing WanderPlanner's own deterministic estimator (zero-variance, free, by construction) against asking GPT-4o-mini/Claude-3.5-Haiku/Gemini-2.5-Flash/Kimi the identical budget question the way an ordinary user would type it into a chatbot directly — no system prompt, no RAG context, no forced JSON. 5 real-anchor-documented cases (BC-001–BC-005: Bengaluru→Colombo, Bengaluru→London, Delhi→Goa, Mumbai→Bangkok, Mumbai→Paris). Scores anchor adherence (directional only — the dataset's own bounds are the estimator's output, not independent ground truth), no-answer rate, false-positive "already told you that" stalls, breakdown rate, hedge-language use, and run-to-run variance. Smoke-tested live end-to-end against real Gemini API (works correctly); not yet run against the full 4-model set (needs `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`MOONSHOT_API_KEY` populated). |
| **Added** Moonshot/Kimi as a 4th eval-only LLM provider | `core/config.py` (`moonshot_api_key`), `eval/llm_providers.py` (`MODEL_REGISTRY` entries + `_call_moonshot`, all `_call_*` functions refactored to accept a `json_mode: bool = True` param so the new freeform-prompt eval doesn't force JSON output), `core/llm_client.py` (Moonshot pricing table entries: `kimi-k2-0711-preview`, `moonshot-v1-8k`). Same "eval-only, not wired into production" scope as the existing OpenAI/Anthropic keys. |
| **Tests** | 24 new unit tests in `tests/unit/test_budget_comparison_scoring.py`, all passing, fully offline (no live API calls). Full backend suite green (335 passed, 6 skipped — same 1 pre-existing unrelated `test_budget_estimator.py` collection error, Python 3.9 `X \| None` syntax issue, confirmed pre-existing via `git stash`). Ruff lint clean on all changed/new files. |
| **Planned, not built** Domestic rail/bus/cab alternative + Kaggle-grounded pricing (follow-up request, same session) | User asked to extend item 10 further: add a rail/bus/cab budget alternative for India-domestic routes (compared against flights, cheaper option called out when >15% cheaper — international stays flight-only), integrate Kaggle flight/hotel datasets with inflation + peak-time multipliers, and plan a long-term data-freshness strategy (free dataset refresh vs. paid APIs). Went through a full plan-mode round (clarifying questions on scope, free-vs-paid stance, Kaggle account ownership) before landing a confirmed plan — **nothing in this workstream has been implemented yet**, it's fully recorded as next-session action items in `docs/NEXT_SESSION_TODO.md`. Verified `Inside Airbnb` (insideairbnb.com) live as a genuinely fresh, free, no-auth international hotel-pricing source (quarterly-refreshed CSVs, CC BY 4.0) but with **zero India coverage** (Mumbai/Goa both 404) — India hotel pricing remains an unresolved gap, flagged rather than papered over. See `docs/NEXT_SESSION_TODO.md`'s new top section for the full plan. |

### v10.30.0 Changes (July 2026) — Pilot OSM/Wikivoyage re-ingestion (8 destinations) + a new Wikimedia 403 root-caused, YouTube hidden-gems groundwork (item 3, key pending)

Picked up item 2 (OSM refresh) and item 3 (hidden-gems alternative source) from `docs/NEXT_SESSION_TODO.md`, both by explicit user direction to scope conservatively rather than batch-run the full 136-destination backlog.

| Change | Detail |
|---|---|
| **Fixed** New Wikivoyage 403 — Wikimedia User-Agent policy non-compliance | Mid-pilot-run, every Wikivoyage request started failing with a 403 directing to Wikimedia's robot policy — a different failure than v10.27.0's markup-parsing bug. Root cause: `NOMINATIM_USER_AGENT` (`wanderplan/1.0` in `.env`, `wanderplanner/1.0` default in `core/config.py`) has no contact info, violating [Wikimedia's User-Agent policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy) (`<client>/<version> (<contact info>)`, "bot" in the name) — confirmed our request rate was far under their documented limits (10 concurrent, 20 req/s), so this was a pure identification-compliance block, not rate-limiting. Fixed in `.env`, `.env.example`, and `core/config.py`'s default: `WanderPlannerBot/1.0 (https://github.com/kunalsmathur-gif/wanderplanner)` (user's choice of contact info — a public repo URL, not a personal email). Live-verified the fix resolves the 403; this UA is shared with Nominatim/Overpass too, which have the same policy requirement. |
| **Fixed** Wikivoyage state/city article ambiguity for "New York" | Even after the UA fix, "New York" kept returning 0 wiki chunks despite a 200 response. Root cause: the naive slug `New_York` resolves to Wikivoyage's **state**-level article (a region/city index with no See/Do/Eat sections) — a different real page from the city guide at `New_York_City`, not a 404, so it silently succeeded with unusable content. Added `scrapers/wikivoyage.py::WIKIVOYAGE_TITLE_OVERRIDES` (currently just `"new york": "New_York_City"`) checked before the naive slug — not exhaustive, add entries as more silent-zero cases like this are found. 3 new tests in `test_wikivoyage_scraper.py`. |
| **Done** Pilot OSM + Wikivoyage re-ingestion (8 of 136 backlogged destinations) | Scoped to the 6 India-domestic metros (statistically likely POC-tester destinations) + 2 major zero-data international cities, per explicit user choice over a full 136-destination batch. New `apps/api/scripts/reingest_pilot_batch.py` (15s between-destination pacing, reuses `ingest_osm_pois()`/`ingest_wikivoyage()`'s existing retry/backoff + orphan cleanup from v10.29.0). **Final live-verified result, all 8/8 destinations fully populated**: Mumbai (60 OSM / 31 wiki), Delhi (60/29), Bengaluru (60/17), Kochi (60/19), Varanasi (60/26), Agra (60/19), Paris (60/32), New York (60/20) — category breakdowns spot-checked well-balanced (no single tag type dominating), confirming v10.27.0's round-robin fix generalizes beyond London. Two transient gaps hit mid-run and closed with a targeted retry: Mumbai's first wiki-embed attempt hit a one-off `torch` meta-tensor race (two concurrent `embed()` calls during initial model load, via `asyncio.gather`) — not investigated further since a plain retry succeeded; New York was the state/city bug above. Local `destination_ingestion_state` rows updated for all 8 so the scheduler treats them as freshly ingested. **Remaining 128 of 136 destinations intentionally not touched this session** — still tracked as `osm-poi-live-reingest`. |
| **Done** Zero-cost hidden-gems fixes (item 3) | `scrapers/reddit.py::SUBREDDITS` gained `"IndiaTravel"` (previously zero India subreddit coverage in the sentiment-mining list, despite `itinerary_corpus.py`'s separate `ITINERARY_SUBREDDITS` already including it). `services/gems.py`'s `_POSITIVE_WORDS`/`_NEGATIVE_WORDS` gained a small romanized Hindi/Hinglish supplement (`badhiya`, `zabardast`, `mast`, `bekar`, `ganda`, `bakwas`, etc.) — deliberately small and low-ambiguity, not exhaustive. 1 new test in `test_gems.py`. |
| **Built and live-verified** YouTube hidden-gems groundwork (item 3) | Every piece written and unit-tested with mocked HTTP/Qdrant first (11 tests in `test_youtube_comments.py`, 2 in `test_gems.py` for blended-source + YouTube-only scoring). New `scrapers/youtube_comments.py`: `search_travel_videos()` (`search.list`, 100 units/query, India-aware query phrasing) + `fetch_video_comments()` (`commentThreads.list`, 1 unit/call, treats a 403 as "comments disabled" — a normal per-video outcome, not burning retries on it) + `ingest_youtube_comments()` (same embed + delete-then-upsert pattern as every other scraper). New `youtube_comments` Qdrant collection wired into `core/qdrant.py::_ensure_collections()` (dimension + destination payload index) and new `youtube_api_key`/`youtube_comments_per_video`/`youtube_videos_per_destination` settings in `core/config.py` + `.env.example`. `services/gems.py::compute_gem_intel_sync()` generalized from a single hardcoded `reddit` collection scroll to blending `reddit` + `youtube_comments` with per-source provenance (`subreddits` field renamed to `sources`, e.g. `"r/travel"` vs `"YouTube"` — confirmed via grep this field is never exposed to the frontend, only consumed internally to build the LLM prompt block, so the rename is safe). User supplied a real `YOUTUBE_API_KEY` mid-session (self-serve, no approval process — unlike Reddit's OAuth gate) — **live-verified end-to-end for Jaipur**: `search_travel_videos()` found 5 real videos, `fetch_video_comments()` pulled 29 real comments (including authentic Hinglish — "Thank you bhaiya Kal ja rahe hu bhaiya"), full `ingest_youtube_comments()` run persisted 131 real chunks to the production Qdrant Cloud cluster. Also re-ingested Jaipur's OSM+Wikivoyage data (60 POIs, 10 wiki chunks — it wasn't in the 8-destination pilot batch above) so the blended scoring had fresh landmark data to match against. **Real finding, not a bug**: `compute_gem_intel_sync("Jaipur")` still returns zero gems/crowd-favourites — the only OSM-POI/comment name match found (Hawa Mahal, 8 mentions) falls in the dead zone between `_GEM_MAX_MENTIONS` (6, "too well-known to be a gem") and `_CROWD_MIN_MENTIONS` (12, "crowd favourite") — deliberately not tuned without real eval data behind it, same principle already documented for the OSM round-robin's per-category cap. Deliberately **not** wired into `services/destination_ingestion.py`'s cold-start gatekeeper or the scheduler yet — that would start spending YouTube quota on every new destination automatically; left as a standalone, manually-invokable ingestion path, same as how OSM/wiki started before scheduler wiring. |
| **Tests** | 17 new tests this session: 3 in `test_wikivoyage_scraper.py` (title override), 11 in new `test_youtube_comments.py`, 1 in `test_gems.py` (Hinglish lexicon), 2 in `test_gems.py` (blended-source scoring, YouTube-only scoring). Full backend suite green (323 passed, 6 skipped), re-run repeatedly through the session as each change landed. |

### v10.29.0 Changes (July 2026) — OSM/Wikivoyage ingestion hygiene: retry/backoff, orphan cleanup, observability gap closed (item 2 prerequisites)

Prerequisite hygiene fixes for `docs/NEXT_SESSION_TODO.md` item 2 (refresh OSM POI data for big cities before POC), landed as their own session ahead of the actual live re-ingestion run. All three gaps had been found and flagged (not fixed) in v10.27.0's POI-pinning investigation.

| Change | Detail |
|---|---|
| **Fixed** No retry/backoff on Overpass/Wikivoyage transient failures | `scrapers/osm.py::fetch_osm_pois()` and `scrapers/wikivoyage.py::scrape_wikivoyage()` both used to silently return `[]` on any request failure, including Overpass's frequent transient `504 Gateway Timeout` under load (hit repeatedly during v10.27.0's live testing, resolved just by retrying seconds later). Both now retry up to 3 attempts with linear backoff (5s/10s) before giving up, logging a WARNING on final exhaustion instead of failing silently. |
| **Fixed** Stale/orphaned Qdrant points accumulate on re-ingestion | Both scrapers upsert by a stable hash of `(destination, name)`/`(url, section, text)` — safe for re-running unchanged logic, but when the selection/chunking logic itself changes (as it did in v10.27.0's round-robin rework), points dropped by the new logic were never deleted, only new ones added. Live-confirmed in v10.27.0: London's `osm_pois` count went 58→112 (not 58→60) after re-ingestion — 60 new points plus ~52 orphaned all-food/drink points from the old logic. New `core/qdrant.py::delete_stale_destination_points()` scrolls a destination-filtered collection and deletes any point not in the freshly-ingested ID set; wired into both `ingest_osm_pois()` and `ingest_wikivoyage()` as a delete-then-upsert per destination. |
| **Fixed** Observability blind spot — silent zero-data ingestion | `services/destination_ingestion.py::ensure_destination_ingested()` now logs a WARNING when a first-time ingestion returns zero OSM POIs *and* zero wiki chunks (previously nothing surfaced this — a destination could silently end up with no grounding data at all). `ingest_wikivoyage()` now returns a chunk count (was previously `None`) so this check has real data to work with. |
| **Live prod Qdrant audit (read-only, no writes)** | Scrolled the real `osm_pois` collection (5,489 points) to get the actual current state instead of relying on stale session notes. Found **105 destinations already ingested**, almost all still capped at ~50-60 points from the pre-round-robin logic and heavily food/drink-dominated (e.g. Copenhagen 100%, Dubai 100%, Bruges 93%, Budapest 95%) — every one needs re-ingestion to actually benefit from v10.27.0's fix. Found **31 destinations never ingested at all** (supersedes the stale `retry_osm_ingest_pass2.py::STILL_ZERO` list): Bangkok, Mumbai, Delhi, Bengaluru, Kochi, Varanasi, Agra, Ho Chi Minh City, Phuket, Maldives, Abu Dhabi, Istanbul, Paris, Prague, Santorini, Oslo, Venice, Reykjavik, Warsaw, Granada, Amalfi, New York, Seattle, Mexico City, Tulum, Medellín, Quito, Vancouver, Casablanca, Fiji, Hawaii. Full list + a dedicated follow-up SQL todo (`osm-poi-live-reingest`) recorded in `docs/NEXT_SESSION_TODO.md`. |
| **Deferred, by explicit user choice** | The actual live re-ingestion run against all 136 destinations (a real production Qdrant write) was intentionally not run this session — user chose to land the code hygiene fixes first and decide re-ingestion scope/pacing in a future session. |
| **Tests** | 15 new/updated unit tests: `tests/unit/test_osm_scraper.py` (retry-then-succeed, exhausted-retries, orphan-cleanup wiring), `tests/unit/test_wikivoyage_scraper.py` (same retry/orphan coverage), `tests/unit/test_destination_ingestion.py` (zero-both-sources warning, no-warning-when-partial), new `tests/unit/test_qdrant_orphan_cleanup.py` (4 tests for `delete_stale_destination_points()` — deletion, no-op when nothing stale, scroll pagination, empty collection). Full backend suite green (328 passed, 6 skipped — the `test_budget_estimator.py` collection error is the same pre-existing/unrelated Python 3.9 `X \| None` syntax issue noted in v10.28.0). |

### v10.28.0 Changes (July 2026) — Thematic-relevance pin fix, data-completeness eval gate, itinerary corpus source expansion, partial budget recalibration + public-dataset research

Follow-up session working through `docs/NEXT_SESSION_TODO.md` items 12, 13, 7, and 10 in that order, plus new research into public datasets for further budget-estimator calibration.

| Change | Detail |
|---|---|
| **Fixed** Borough Market / Harry Potter recurring precision miss (item 12) | `services/poi_pinning.py`'s wiki-fallback verification (`verify_candidates_sync`) previously confirmed a candidate name was *mentioned* anywhere in a destination's full Wikivoyage text blob, with zero check that the mention was actually related to the user's named interest — the exact reason "Borough Market" kept getting pinned for a "Harry Potter" interest in London (flagged in the 2026-07-13 live run, reproduced again in v10.27.0). Added `_interest_keywords()`/`_INTEREST_STOPWORDS`; the wiki fallback now requires the matched chunk to co-occur with an interest keyword before counting as verified — text is kept as per-chunk instead of one joined blob so this co-occurrence check is meaningful. A wiki mention with no thematic tie is now dropped rather than force-pinned. **Scope note:** only the wiki path was touched; the OSM path (exact-name match against curated map nodes) still has no thematic check, so "verified" ≠ "relevant" is still a live distinction in general. Three new regression tests in `tests/unit/test_interest_pinning.py`. |
| **New** Data-completeness pre-flight eval gate (item 13) | `eval/data_completeness_scoring.py` (pure scoring: `MIN_WIKI_CHUNKS=1`, `MIN_OSM_POIS=20`, `MAX_CATEGORY_SHARE=0.5`) + `eval/run_data_completeness_check.py` (runner — scrolls the real `wiki`/`osm_pois` collections for the same 16 destinations the refinement-fidelity dataset exercises, via `services.gems._scroll_destination`). Checks per destination: non-zero wiki chunk count, a minimum OSM POI count, no single OSM tag category exceeding a dominance share — directly targets the class of bug v10.27.0 found (category starvation, a silently-broken scraper) that the offline fidelity/honesty harness structurally cannot detect, since its fixtures are self-contained by design. Tracked as its own pass-rate gate, separate from `fidelity`/`honest`. 12 new unit tests (mocked Qdrant). Not yet wired into CI or run against the live production cluster. |
| **Expanded** Itinerary corpus travel-blog source pool (item 7) | `scrapers/itinerary_corpus.py`'s `TRAVEL_BLOG_FEEDS` previously had Nomadic Matt (working) and Planet D (broken, connection-reset). Live-tested ~15 candidate RSS feeds; replaced Planet D with **Uncornered Market** (general adventure/hiking, good itinerary-title hit rate) and added **Bruised Passports** (India-focused — closes the gap that the blog-feed pool had zero India-specific coverage even though `ITINERARY_SUBREDDITS` already lists `r/IndiaTravel`). Both live-verified for full-body HTML extraction before wiring in. **Live-ingested into production** (user-confirmed write): `ingest_itinerary_corpus()` run against the real Qdrant Cloud cluster, `itinerary_corpus` collection went from 1 → 4 real points (Nomadic Matt/Madrid, Bruised Passports/Australia, /Doha, /Kyrgyzstan). One Uncornered Market/Cyprus doc failed LLM extraction (`json.JSONDecodeError`) after 2 retries — a separate extraction-robustness issue, not a source-pool problem, tracked as a follow-up if it recurs. |
| **Partial** Budget-estimator hand-authored figure recalibration (item 10) | Built `apps/api/scripts/recalibrate_pricing.py` (documented browser-link checklist for remaining flight bands/cost tiers + `recalibrate_band()`/`recalibrate_cost_matrix()` — rescales one anchor and nudges only violating neighbours enough to preserve monotonic ordering, never regressing an already-correct neighbour; 11 new unit tests confirm it never mutates the real tables it reads). Applied three real anchors this session to `core/distance_pricing.py`'s `DISTANCE_BANDS`, gathered from real MakeMyTrip searches (screenshots): near-neighbour (Bengaluru→Colombo, ~₹27,000 round trip) and long-haul (Bengaluru→London, ₹67,327 round trip, Aug 2026) were recalibrated via the full anchor+nudge algorithm; regional's low end was manually adjusted down (not the tool's full symmetric rescale, to avoid also dropping the band's high end, which prices genuinely pricier international-regional routes like Bangkok/Dubai that a domestic Delhi→Goa anchor says nothing about) after a real Delhi↔Goa peak-season (Dec 25–31) fare (₹18,157 round trip) landed 4km past the domestic/near-neighbour cutoff and undershot the old regional low end even at holiday pricing. **Still unrecalibrated:** regional's high end, ultra_long_haul (already consistent, no anchor needed), and all of `core/budget_estimator.py`'s `_COST_MATRIX` (moderate/premium stay/food tiers). |
| **Research (not yet applied to code)** Public dataset survey for further calibration | Three background research passes, citation-backed: (1) **India-domestic flight fares** — best pick is Kaggle "Flight Price Prediction" (shubhambathwal, 300K rows, CC0, 6-metro EaseMyTrip data, Feb–Mar 2022) plus a MachineHack 2019 set for cross-validation; no dataset found covers India-origin international routes; recommends a ~1.15–1.25× nominal uplift for 2022→2026 and notes relative distance-band ratios are stable even though absolute INR is stale. Both require a Kaggle account/API token (no anonymous download). (2) **Indian Railways fares** — no official downloadable per-km table exists (CRIS/PRS uses a private telescopic distance-slab lookup); back-calculated approximate ₹/km slabs from real seat61.com fares (LOW-MEDIUM confidence, ±15–20%), with HIGH-confidence surcharges confirmed (reservation charges, superfast surcharge, 5% GST on AC classes only, Tatkal 10%/30% of base, train-type multipliers). Recommends validating against `erail.in/train-fare` before production use. (3) **World flight/hotel datasets** — researched in parallel (US DOT/BTS DB1B, Expedia-scrape "Flight Prices", Inside Airbnb per-city listings, Kaggle "Hotel Booking Demand", etc.) as candidate sources for a worldwide fare-band model and a global/Indian hotel cost-tier model. None of this research has been applied to `_COST_MATRIX` or `DISTANCE_BANDS` yet — it's reference material for continued recalibration, most of it gated on setting up Kaggle API access. |
| **Tests** | Full backend suite green throughout (315 passed, 6 skipped, 1 pre-existing unrelated collection error in `test_budget_estimator.py` — Python 3.9 `X \| None` syntax issue, confirmed pre-existing via `git stash`). |

### v10.27.0 Changes (July 2026) — POI-pinning ("Harry Potter test") root-caused end-to-end: OSM landmark starvation + Wikivoyage scraper silently broken for every destination

The v10.17 hard-constraints/pinning feature (see below) had never actually worked in production — verifying it live (per `docs/NEXT_SESSION_TODO.md` item 5) surfaced three stacked bugs, not one. Full narrative + at-scale findings + follow-up TODOs in `docs/NEXT_SESSION_TODO.md`'s "POI-pinning investigation" section; summary here.

| Change | Detail |
|---|---|
| **ROOT CAUSE 1** OSM ingestion was 100% food/drink, 0% landmarks | `scrapers/osm.py::_build_overpass_query()` unioned all POI tag categories into one Overpass call with a single flat result cap; in dense city centers, food/drink venues vastly outnumber landmarks, so the cap filled entirely with restaurants/cafes/bars before Overpass ever returned a museum or monument. Live-confirmed: London's already-ingested 58 POIs were 58/58 food & drink. |
| **FIXED** Over-fetch + round-robin category selection | `_build_overpass_query()` now requests up to `min(max_results * 5, 400)` raw results instead of exactly `max_results`; `_prioritize_landmarks()` rewritten from a simple "food/drink last" stable sort to a **round-robin across every category present** (food/drink still drawn from last). The simpler stable-sort version was tried first and found insufficient at scale — see next row. |
| **FOUND (checking scale)** Stable-sort alone just relocates the starvation bug | Live-verified against Paris/Tokyo (read-only fetch, no ingestion): with only "food/drink last" in place, Paris returned 51/60 "train station" nodes (dense metro network) and Tokyo returned 40/60 "place of worship" nodes (shrines/temples are everywhere) — both cases crowding out museums/attractions/theatres almost as badly as the original bug, just via a different dominant category. Round-robin measurably improved this (Paris train-stations 51→35, Tokyo places-of-worship 40→28, every other category roughly doubled) but does not fully equalize categories when one is far more numerous within the ingestion radius than all others combined — documented as an open follow-up, not solved. |
| **Expanded tag coverage** | `POI_TAG_QUERIES` grew from 14 → ~28 categories: added heritage/historic (ruins, archaeological sites, memorials, artwork, zoo, aquarium, theme park), arts/science/entertainment (theatre, arts_centre, cinema), sports (stadium, sports_centre), nature/photo-worthy (garden, nature_reserve), and transportation landmarks (railway=station, aeroway=aerodrome). Per explicit user direction, this expansion is destination-level/unbiased — no per-user preference weighting (e.g. "toddler → more parks") was added at the ingestion layer; that's scoped as a separate downstream retrieval/generation concern if built later. |
| **ROOT CAUSE 2** Wikivoyage scraper silently broken for every destination | `scrapers/wikivoyage.py::scrape_wikivoyage()` walked `h2.find_next_siblings()` to collect section content, but MediaWiki's current skin wraps each `<h2>` in a `<div class="mw-heading">` — once that wrapper was introduced, the walk only ever found the wrapper's own (empty) children, never the real paragraphs/lists, so **every** destination's Wikivoyage scrape silently returned 0 chunks. This is the same "wiki collection has 0 points" gap already flagged (but not root-caused) in v10.26.0's budget-estimator RAG-grounding work. |
| **FIXED** | Walk siblings of the heading's `mw-heading` wrapper div when present, falling back to the bare `<h2>` for older/other markup, stopping at the next heading (wrapper or bare) so content doesn't bleed across sections. Verified generalizes beyond London: re-scraped (read-only) Paris (32 chunks), Tokyo (48 chunks), New York City (20 chunks) — all previously 0. |
| **Live end-to-end verification** | Re-ingested London's OSM POIs + Wikivoyage text with both fixes, replayed the "I'm a huge Harry Potter fan" chat-refine call: `pinned_pois` is no longer empty — Borough Market correctly verified (via the wiki fallback, `verified_by: "wiki"`) and pinned; genuinely unverifiable candidates (Warner Bros. Studio Tour — actually ~30km outside the ingestion radius; Platform 9¾ — not a separately OSM-tagged node) correctly listed as dropped rather than invented. |
| **Not fixed — documented follow-ups** | No hard per-category cap (round-robin fairness only); no popularity/notability signal within a category (famous-but-unlucky nodes like Leadenhall Market/Millennium Bridge can still lose the truncation lottery); stale Qdrant points from earlier ingestion-logic versions are never cleaned up on re-ingestion (London's `osm_pois` count went 58→100, ~40 orphaned); no retry/backoff on transient Overpass 504s or Wikivoyage fetch failures (both silently return empty). All four tracked in `docs/NEXT_SESSION_TODO.md`'s operational-hygiene list. |
| **Tests** | New `tests/unit/test_osm_scraper.py` (7 tests: landmark prioritization, round-robin category fairness, truncation, network-failure handling) and `tests/unit/test_wikivoyage_scraper.py` (3 tests: mw-heading-wrapped markup, legacy markup, section-boundary isolation). Also fixed a stale pre-existing test, `tests/integration/test_auth.py::test_signup_rejects_duplicate_email` (asserted a generic message; the code intentionally returns a more specific one per an existing product-decision comment — noted as a known-stale test in v10.26.0, actually fixed this session). |
| **Follow-up (same day)** UX copy for unverified candidates | `chains/chat_refine_chain.py::_apply_interest_pinning()` reply text updated to advise checking Google Maps/Reddit reviews before planning around unverified places, not just "we left this out." |
| **Follow-up (same day)** Eval-criteria implications | Live re-testing surfaced that "Borough Market" is being pinned again for London/Harry Potter — a real place, correctly verified as *existing* (via the wiki fallback), but with no genuine Harry Potter connection: a known, previously-flagged (2026-07-13 live run), still-open precision miss, distinct from the two root causes above. This prompted an eval-criteria review: `eval/refinement_scoring.py`'s metric *definitions* don't need to change, but its docstring now carries explicit caveats that "honest"/"verified" measure existence, not thematic relevance or data completeness, and `docs/eval-set.md` §4V gained a matching "structural limitations" subsection. A new data-completeness pre-flight check (against the real Qdrant cluster, not eval fixtures) is recommended but not yet built — see `docs/NEXT_SESSION_TODO.md` items 12-13. |

### v10.26.0 Changes (July 2026) — Budget estimator distance/RAG-grounding overhaul + production cross-origin auth cookie fix

Two independent bug investigations from live user testing on the production Vercel/Railway deployment.

**1. Budget estimator: flight/stay/food no longer ignore real geography.**

| Change | Detail |
|---|---|
| **FIXED** Flight cost ignored departure city entirely | `core/budget_estimator.py` used one flat hand-authored number per destination cost tier, regardless of where the traveller was flying from — a Delhi→Colombo and a Chennai→Colombo trip got the exact same "flight" line item. Real user report: app quoted ~₹9,166/person for Bengaluru→Colombo when the real fare (checked by the user for Nov 2026) was ~₹27,000 round trip, a ~2.4x miss, and Anya never even asked which city the user was flying from. |
| **NEW** `core/distance_pricing.py` | Extracted the haversine distance-band heuristic (previously private to `core/cost_grounding.py`) into a shared pure module. Bands recalibrated against the real ₹27,000 Bengaluru→Colombo data point (near-neighbour band widened from ₹7,000–15,000 to ₹12,000–30,000); other bands nudged up to preserve monotonic ordering but are NOT independently verified — recalibrate the same way once a real fare turns up for one of them. |
| **NEW** Origin-required gate | `budget_estimate_prompt_hint()` now blocks quoting a flight-inclusive number until departure city is known, mirroring the existing group-size gate (skipped if the user's flights are already prebooked). `chains/wizard_chat_chain.py` geocodes origin+destination server-side (reusing `services/geocode.py`, the existing Nominatim proxy) once group+destination+origin-city are all known — not every turn, to avoid hammering the rate-limited free geocoder — and persists the resolved coordinates back into `config_patch` so it's a one-time cost per conversation. |
| **NEW** `core/price_extraction.py` + RAG grounding for stay/food | `core/budget_estimator.py`'s stay/food components now try a real per-destination figure first — the median of community-reported nightly-rate/daily-spend mentions pulled from the app's existing free RAG collections (Reddit/Wikivoyage), via deterministic regex extraction (NOT an LLM call — an LLM call here would recreate the exact "let the model guess a number" problem this module exists to avoid) — falling back to the hand-authored flat table when that comes up empty. **As of this session the Reddit/Wikivoyage Qdrant collections are empty in production** (0 points each, verified live against the real cluster — Reddit ingestion has been broken for months, see `docs/NEXT_SESSION_TODO.md`), so this falls back to the flat number for virtually every destination today; the plumbing is in place for when ingestion is fixed. |
| **FIXED** Food estimate was ~2-2.5x low | Real research (Sri Lanka, budget tier): mid-range dining runs ~$20-25/person/day vs. the old flat ₹800/day. `food_per_day_pp` recalibrated across all three destination tiers off that one anchor point (budget/mid_range). `stay_per_night_pp` was checked against the same research (~$50/night Colombo double room ≈ ₹2,075/person) and found already close to the existing ₹2,000 figure — left unchanged rather than "fixed" without evidence it was wrong. |
| **Async propagation** | `estimate_bare_minimum_budget()`/`budget_estimate_prompt_hint()` are now `async` (the RAG lookup requires it) — updated call sites: `chains/wizard_chat_chain.py`, `chains/feasibility_chain.py::_safe_bare_minimum()`, `services/comparison.py::_compare_bare_minimum_budget()` (now runs per-destination estimates concurrently via `asyncio.gather`). |
| **Tests** | 27 new unit tests (`test_budget_estimator.py`, `test_price_extraction.py`, `test_wizard_budget_geocode.py`) — full backend suite green (258 passed, 6 skipped). |

**2. Production auth loop: cross-origin session cookies were being silently dropped.**

| Change | Detail |
|---|---|
| **ROOT CAUSE** `COOKIE_SAMESITE=lax` in a cross-origin deployment | Frontend (Vercel) and backend (Railway) are different origins, but the session cookie config (`core/config.py`) defaulted to `SameSite=Lax` — browsers don't attach `SameSite=Lax` cookies to cross-site fetch/XHR requests, only top-level navigations. This one misconfiguration explained three separate-looking user reports: a signed-in user got asked to sign in again during generation (`/auth/me` 401'd despite a valid cookie in the jar), signup then correctly rejected the resulting duplicate-account attempt (the user genuinely already had an account — the app just couldn't see the session), and signing back in appeared to loop forever (the local Zustand auth store was set to `authenticated` from the login response body without ever confirming the cookie round-tripped, so the very next authenticated call — `/api/generate-itinerary` — 401'd the same way). |
| **FIXED in Railway env vars** | `COOKIE_SAMESITE` set to `none` in production (confirmed working after redeploy). |
| **NEW** Startup safety validator | `core/config.py` gained a `model_validator` (same pattern as the existing `jwt_secret` production check) that now refuses to start if `ENVIRONMENT=production` and `COOKIE_SAMESITE=lax`, or if `COOKIE_SAMESITE=none` without `COOKIE_SECURE=true` — fails loudly at deploy time instead of shipping this silently again. `.env.example` and `docs/system-design.md`'s env var table corrected to stop suggesting `lax` is fine in production. |
| **NEW** Silent token-refresh-on-401 (independent secondary bug) | The 15-minute access token had a working `/auth/refresh` endpoint on the backend that nothing on the frontend ever called — any session idle past 15 minutes (an easy threshold for a multi-turn wizard conversation) would reproduce the same symptoms even with SameSite fixed. `lib/authApi.ts` gained `refreshSession()`; `store/authStore.ts`'s `hydrate()` now tries it before concluding logged-out; `lib/api.ts`'s `streamItinerary()` now retries once via silent refresh on a 401 before surfacing `AUTH_REQUIRED`. |
| **Tests** | New `tests/unit/test_config_validation.py` (4 tests) for the validator; full existing `tests/integration/test_auth.py` + `test_itinerary_gating.py` suites still green except one **pre-existing, unrelated** failure (`test_signup_rejects_duplicate_email` expects a generic error string; the actual code intentionally returns a more specific message per an existing product-decision comment — stale test, not introduced this session, not yet fixed). Frontend type-checks clean; manually verified signup → reload → session-recognized flow in a live browser. |

### v10.25.0 Changes (July 2026) — Eval infrastructure hardening: wizard harness, LLM-as-judge, compare/analyze tools, externalized config

A review of the existing eval harnesses (`run_rag_eval.py`/`run_red_team_eval.py`/`run_model_comparison.py`) against the standard "Quality Flywheel" methodology (dataset → inference → grading → failure analysis → optimize) surfaced 6 gaps; all 6 fixed this session. See §8A above for the new architecture and `docs/eval-set.md` §7 for the full process-discipline write-up.

| Change | Detail |
|---|---|
| **NEW** Anya wizard multi-turn eval harness | `eval/run_wizard_eval.py` + `wizard_dataset.json` + `wizard_checks.py` — first automated coverage of the wizard chat flow (previously only manually tested per `docs/eval-set.md`). Replicates `LLMWizard.tsx`'s one-level-deep `config_patch` → `partial_config` merge exactly in Python. Regression-checks the exact 2026-07-18 production bug (budget-confirmation reply showing stale pace chips). Live-verified 10/10 turns passing. |
| **NEW** LLM-as-judge quality metric | `eval/judge_metrics.py` — scores tone/personalization/coherence (1-5) via a fixed `gemini-2.5-flash` judge, independent of whichever model is under test in `run_model_comparison.py`, so judging can't bias one candidate. Returns `None` (not a zero score) on any failure so a missing API key doesn't tank a model's aggregate. Wired into `model_comparison_scoring.py`'s aggregation and report rendering. |
| **NEW** Baseline/candidate compare + failure-analysis tools | `eval/compare_results.py` diffs two timestamped result files metric-by-metric (auto-detects wizard vs. red-team/model-comparison result shape, correct "higher/lower is better" polarity per metric, exit code 1 on regression). `eval/analyze_results.py` clusters failing cases by category (red-team), failure reason (model-comparison), or check name (wizard) instead of a flat per-case list. Both harness runners now write timestamped `out/<name>_results_<ts>.json`/`.md` (plus a fixed-name "latest" alias) instead of overwriting one file per run. |
| **NEW** Externalized metrics config | `eval/eval_config.json` + `config_loader.py` — which wizard checks run, judge enabled/model, default `--runs`/`--scale`, and failure-analysis thresholds are now all in one file, overridable per-invocation via CLI flags without editing runner code. |
| **DOCS** | Process-discipline rules (don't lower thresholds to pass, don't skip flaky cases, don't fix the expected output instead of the agent, don't self-judge, don't treat judge=None as zero) documented in `docs/eval-set.md` §7; product-facing "types of evals" framing added to `docs/PRD.md` §10; architecture documented in `docs/system-design.md` §15A and here in §8A; noted in `docs/itinerary-generation-flow.md` and `docs/GTM_STRATEGY.md` roadmap. |

### v10.24.0 Changes (July 2026) — Critical Qdrant payload-index fix (RAG retrieval was silently broken since the Cloud migration); demand-driven ingestion implemented; google-genai 2.10.0 upgrade

Backend-only, no frontend changes. Two separate threads: (1) implementing the demand-driven ingestion design from `docs/scaling-tech-challenges.md` §8, which led to discovering (2) a production-critical bug while testing against the real Qdrant Cloud cluster for the first time.

| Change | Detail |
|---|---|
| **FIXED (critical)** Missing Qdrant payload indexes — RAG retrieval silently degraded in prod | Qdrant Cloud rejects filtered `scroll`/`search` queries (e.g. `FieldCondition(key="destination", ...)`, used throughout `services/search.py`/`gems.py`/`rag_fallback.py`) with a 400 if no payload index exists on that field. `:memory:` mode (used through local dev/testing until this session) doesn't enforce this, so the gap was invisible until a real filtered query hit the actual Cloud cluster. Because `generate_itinerary()` wraps the live-LLM call in try/except → fallback chain, this never surfaced as a user-facing error — it silently meant **no real RAG context reached the LLM prompt since the Cloud migration**, degrading itinerary grounding without any visible symptom. `core/qdrant.py::_ensure_collections()` now creates a `KEYWORD` index on `destination` for `wiki`/`reddit`/`osm_pois`/`itinerary_corpus` on every connect (idempotent). **Requires a Railway restart/redeploy to take effect** — index creation runs once per process start, not retroactively against an already-running process. See `docs/system-design.md` §9 and `docs/itinerary-generation-flow.md` for full detail. |
| **NEW** Demand-driven ingestion (`docs/scaling-tech-challenges.md` §8, now implemented) | New Postgres `destination_ingestion_state` table (migration `0004_destination_ingestion_state`) + `services/destination_ingestion.py::ensure_destination_ingested()` gatekeeper — geocode-validates a destination on first request, ingests OSM POIs + Wikivoyage inline (stampede-safe via per-destination `asyncio.Lock`), wired into `chains/itinerary_chain.py::generate_itinerary()`. `core/scheduler.py::_refresh_osm_pois` rewritten to refresh only stale rows in the state table instead of looping the old fixed 134-city `KNOWN_DESTINATIONS` list. Verified end-to-end with a genuinely new destination ("Ubud") not in the old static list. |
| **FIXED** Local dev `.env` was pointing at `:memory:` instead of the shared Qdrant Cloud cluster | An earlier session's migration hadn't stuck locally — corrected with the real cluster credentials; local ingestion scripts now actually persist. Ran two OSM POI retry passes (6s then 12s delay) against the corrected cluster: 105 distinct destinations now have real OSM data (up from 48), 59 of the original 92 missing/low-coverage destinations fixed; ~33 remain Overpass-rate-limited even at 12s delay. Backfilled `destination_ingestion_state` for all 105 so the new scheduler keeps them fresh. |
| **UPGRADED** `google-genai` 1.2.0 → 2.10.0 (dependabot PR #8) | Also bumped transitive `pydantic` 2.7.1→2.13.4 and `httpx` 0.27.0→0.28.1. Added `ThinkingConfig(thinking_budget=0)` to `chains/interest_expansion_chain.py` and `chains/extract_trip_chain.py` — 2.5-flash was spending `max_output_tokens` on hidden thinking before the visible JSON, previously requiring an inflated 2048-token cap to avoid truncation; `thinking_budget=0` eliminates that consumption, so `interest_expansion_chain.py`'s cap dropped back to the originally-intended 512 (live-verified against real Gemini with a Harry Potter/London query — full untruncated 10-item list). |
| **INVESTIGATED** Reddit ingestion confirmed broken in production too | Railway logs show 403 Blocked on every `_refresh_reddit` run (startup + every scheduled 6h execution) since the Cloud migration — this isn't a sandbox-network quirk, Reddit is blocking the request pattern everywhere. Reddit's API access policy has also tightened significantly: no more instant self-serve script keys — requires a dedicated bot account and a written app-review request. Submitted 2026-07-16 (description covers both the sentiment-mining and itinerary-example-search flows, subreddit list, request volume, retention policy); **pending Reddit's approval, no ETA**. Once approved, `scrapers/reddit.py::ingest_reddit()` needs rewiring from the current unauthenticated `httpx.get()` calls to OAuth2. |
| **Verified** | Full backend suite: 260/261 passed (1 pre-existing unrelated `test_auth.py` copy-mismatch failure, confirmed unrelated via inspection). Payload-index fix live-verified against the real Cloud cluster (`rag_skeleton_itinerary()` and `retrieve_context()` both 400'd before, work correctly after). Demand-driven gatekeeper live-verified end-to-end. No frontend changes — `tsc`/web suite not applicable. |

### v10.23.0 Changes (July 2026) — Eval recall chase: anti-distractor rule tuned; live rerun PUBLISHED (fidelity 0.983, up from 0.975)

Follow-up to v10.20.0's published live run. The published report's 3 recall misses (RF-001 London, RF-009 LA, RF-012 Mumbai) were investigated at the prompt level rather than accepted as noise.

| Change | Detail |
|---|---|
| **INVESTIGATED** `chains/interest_expansion_chain.py` misses | Cheap direct probes of `expand_interest_to_candidates()` (not the full $0.40 live pipeline) on the 3 failing cases showed the anti-distractor rule's "known FOR the interest itself" wording was too conservative: it was excluding **Hollywood Walk of Fame** (RF-009 LA movie-studios interest) and **Prithvi Theatre** (RF-012 Mumbai Bollywood interest) — both true positives in the truth-set, dropped because they're famous *for* celebrities/cinema rather than literally named after the interest. |
| **TUNED** `_EXPANSION_SYSTEM_PROMPT` | Added a clarifying bullet to the anti-distractor rule explicitly allowing famous theatres, walk-of-fame monuments, and publicly-known celebrity residences to count as "specific" to a named interest. One prompt-text change, no code-path change. |
| **Validated before touching the published numbers** | Re-probed all 3 originally-failing cases directly (all fixed); spot-checked 4 other positive cases and all 4 negative/honesty cases for regressions (none — the pre-existing Kyoto scuba-diving cross-city candidate issue is unrelated, filtered by verification not this prompt); offline regression gate unaffected at 1.000 (by construction — it never calls the LLM); full backend suite **255 passed** (2 pre-existing unrelated failures — `test_auth.py::test_signup_rejects_duplicate_email`, `test_rag.py::test_fallback_tier2_rag_skeleton_builds_from_osm_pois` — confirmed present on unmodified `main` via `git stash`, not caused by this change). |
| **Live rerun** (gemini-2.5-flash, 2026-07-15, after founder raised the Gemini spend cap) | **Fidelity 0.983 (was 0.975) · recall 0.958 (was 0.938) · inclusion 1.000 · stability 1.000 · precision 0.979 · honesty 4/4.** RF-009 and RF-012 (the rule-caused misses) now score 1.00. RF-001 still missed one place and a new miss appeared at RF-015 (Amritsar Sikh heritage, missing "Golden Temple") — re-probing both directly afterward confirmed they succeed in isolation, i.e. these are `temperature=0.1` sampling-variance misses, not a residual defect in the tuned rule. The aggregate trend (0.975→0.983, 0.938→0.958) is real; which specific 3 cases miss on any single run is noisy by design. |
| **PUBLISHED** `docs/eval-results/` updated | `README.md` rewritten with the 2026-07-15 numbers, the tuning rationale, the 3-way validation done before publishing, and an explicit honest explanation of why the miss set shifted case-by-case. New dated verbatim reports `report_vs_chatgpt_2026-07-15.md` / `report_vs_claude_sonnet_2026-07-15.md` added alongside the original 2026-07-14 pair (kept for the historical record). Propagated the before/after numbers into `docs/GTM_STRATEGY.md` §5 Phase 1 item 4, `docs/eval-set.md` §4V, and the pitch deck (`docs/pitch-deck/index.html`, which had drifted to a stale pre-v10.20 figure). |
| **Verified** | See validation row above; no frontend changes this entry, `tsc`/web suite not applicable. |

### v10.22.0 Changes (July 2026) — UI/UX audit §2.3–§2.5: on-demand PDF, one currency/date formatter app-wide, BestTime label clarity

Second UI/UX-audit milestone of the session. All deterministic, zero-LLM; the PDF change is also a bundle/CPU win.

| Change | Detail |
|---|---|
| **REWRITTEN** `PdfDownloadButton.tsx` — on-demand generation (audit §2.3) | `<PDFDownloadLink>` rendered the full PDF to a blob **on every dashboard mount** whether or not the user downloaded. The button now builds the blob only on click via `pdf().toBlob()`, and `@react-pdf/renderer` + `ItineraryDocument` are dynamic-imported at click time — the ~1 MB renderer leaves the dashboard bundle entirely. Failure shows an inline "Could not generate the PDF — please try again." instead of silently dying. |
| **NEW** `lib/format.ts` — the one formatter pair (audit §2.4) | `formatCurrency(amount, code)` (`Intl.NumberFormat('en-IN', {style:'currency'})`, whole units, malformed-code fallback to a plain label) and `formatDayDate(iso)` ("2026-11-14" → "Sat, 14 Nov"; non-ISO input passes through). 8 unit tests. |
| **UPDATED** currency call sites | Trip Metrics budget (`Column1Metrics` — was browser-locale `INR 150,000`, now `₹1,50,000` matching the landing page), `ExpenseBreakupCard`/`FeasibilityCard` fmt helpers, `ConversationalWizard.formatBudget`, `LLMWizard` resume-summary line (was browser-locale). Chat strings already on `en-IN` grouping were left alone; the PDF document keeps its deliberate `Rs.` prefix (font glyph). |
| **UPDATED** date call sites | Day tabs (`ItineraryTimeline`), share page (`t/[slug]`), and `ItineraryOverview` day list now render "Sat, 14 Nov" instead of raw ISO. |
| **UPDATED** `CurrencyWidget` + `BestTimeWidget` (audit §2.4/§2.5) | Failure copy softened to "Rates temporarily unavailable."; BestTime's confusing "🎯 Peak" (overlapping "Best months") is now "👥 Busiest (crowds & prices)" and "💤 Off-season" is "💤 Quietest" — reconciled with the crowd-preference language elsewhere. Both widgets also moved off light-only slate classes onto the `--_*` tokens (same gap class as §2.1, fixed while touching them). |
| **Verified** | `tsc --noEmit` clean · web suite 44 passed (36 + 8 new `format.test.ts`). |

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

**Follow-up (2026-07-29 + 2026-07-30):** the self-service "Request admin access" button/section was removed from `/account` — a pre-revenue, single-operator pilot has no real use case for a self-serve request surface, only added attack surface. The `POST /admin/requests` API and `/admin` approve/reject panel are unchanged and still work if a request is created some other way, but there's no in-app path to create one anymore. Admin access is now granted purely as a backend action via the new `apps/api/scripts/grant_admin.py <email>` CLI (idempotent, run directly against the database) — used to grant `kunal.s.mathur@gmail.com` admin access in production. See `docs/system-design.md` §8A and `docs/PRD.md` Clarification #13 for the full writeup.

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
