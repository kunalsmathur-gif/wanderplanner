# WanderPlanner — System Design Document

**Version:** 8.3 (Accounts · Auth Gate · Password Reset · Analytics)
**Last Updated:** July 7, 2026  
**Audience:** Engineering team and technical stakeholders

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Data Flow: LLM Anya Wizard](#2-data-flow-llm-anya-wizard)
3. [Data Flow: Start Anywhere](#3-data-flow-start-anywhere)
3A. [Data Flow: Authentication (Signup / Login / Google SSO / Password Reset)](#3a-data-flow-authentication-signup--login--google-sso--password-reset)
3B. [Data Flow: Account Deletion & Data Purge](#3b-data-flow-account-deletion--data-purge)
3C. [Data Flow: Admin Access Request & Approval](#3c-data-flow-admin-access-request--approval)
4. [Data Flow: Itinerary Generation with RAG](#4-data-flow-itinerary-generation-with-rag)
5. [Data Flow: Persistent Anya Chat](#5-data-flow-persistent-anya-chat)
6. [Data Flow: Share Trip Link](#6-data-flow-share-trip-link)
7. [Data Flow: Voice Interaction](#7-data-flow-voice-interaction)
8. [API Contract](#8-api-contract)
8A. [Database Schema](#8a-database-schema)
9. [Qdrant Collection Schema](#9-qdrant-collection-schema)
9A. [Admin Analytics & Cost Tracking](#9a-admin-analytics--cost-tracking)
10. [Gemini Prompt Design & Temperature Settings](#10-gemini-prompt-design--temperature-settings)
11. [Frontend State Architecture](#11-frontend-state-architecture)
12. [Design System](#12-design-system)
13. [Environment Variables Reference](#13-environment-variables-reference)
14. [Performance & Cost Analysis](#14-performance--cost-analysis)
15. [Resilience & Retry Architecture](#15-resilience--retry-architecture)

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          BROWSER (Desktop)                               │
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  Next.js 16 (Turbopack) + TypeScript                             │   │
│  │  Design System: Space Grotesk + DM Sans + JetBrains Mono        │   │
│  │  Theme: Light / Dark (CSS custom properties, no-flash script)   │   │
│  │                                                                   │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │  LandingHero  (shown when no itinerary loaded)            │  │   │
│  │  │  - Hero headline + "Start planning with Anya" CTA         │  │   │
│  │  │  - Start Anywhere: URL/text input → extract-trip API      │  │   │
│  │  │  - Feature grid (4 cards)                                 │  │   │
│  │  │  - Inspiration gallery (12 cards, Wikipedia photos)       │  │   │
│  │  │  - FAQ section (JSON-LD SEO)                              │  │   │
│  │  │  - Nav anchors: Inspiration · FAQ                         │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  │                                                                   │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │  LLMWizard — Full-screen Overlay (LLM-powered)       │  │   │
│  │  │  🎙️ Voice Mode: SpeechRecognition + SpeechSynthesis  │  │   │
│  │  │  💬 Natural conversation with Gemini 2.5 Flash        │  │   │
│  │  │  🏷️ 6-field progress pills + chip quick-replies       │  │   │
│  │  │  🎯 WizardPreload: inspiration/URL click pre-fills    │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  │                                                                   │   │
│  │  ┌──────────┐  ┌──────────────────────────┐  ┌───────────────┐  │   │
│  │  │ Column 1 │  │       Column 2            │  │   Column 3    │  │   │
│  │  │  (20%)   │  │        (55%)              │  │    (25%)      │  │   │
│  │  │          │  │                           │  │               │  │   │
│  │  │ Metrics  │  │ [destination · ShareBtn]  │  │ Map (Leaflet) │  │   │
│  │  │ Expense  │  │ ItineraryTimeline         │  │ ⤢ Full screen │  │   │
│  │  │ Currency │  │  PolaroidCard activity    │  │ Best Time     │  │   │
│  │  │ Booking  │  │  cards (wiki photos)      │  │ Travel Tips   │  │   │
│  │  │   Hub    │  │ ComparisonPanel           │  │               │  │   │
│  │  └──────────┘  └──────────────────────────┘  └───────────────┘  │   │
│  │                                                                   │   │
│  │  Floating: Anya Orb → ChatPanel (post-gen persistent chat)      │   │
│  │                                                                   │   │
│  │  Zustand (6 stores):                                             │   │
│  │  appStore · tripConfigStore · wizardChatStore                    │   │
│  │  itineraryStore · chatStore · bookingStore                       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────────────┘
                              │ HTTPS / JSON / SSE
┌────────────────────────────▼────────────────────────────────────────────┐
│                    FastAPI (Python 3.9+) Port 8000                        │
│                                                                            │
│  POST /api/wizard-chat         → Anya LLM wizard (Gemini 2.5 Flash)  ⭐NEW  │
│  POST /api/generate-itinerary  → Gemini 2.5 Flash (5× retry + fallback) │
│  Photo enrichment              → Pexels hero-photo lookup (best-effort)   │
│  POST /api/chat-refine         → Anya post-gen chat handler              │
│  POST /api/recommend-cities    → City suggestions (Gemini)               │
│  POST /api/extract-trip        → URL/text → trip fields (Gemini) ⭐NEW  │
│  POST /api/share               → Serialize trip → slug          ⭐NEW   │
│  GET  /api/share/{slug}        → Read-only trip data            ⭐NEW   │
│  GET  /api/travel-tips         → Gemini tips (cached 1h)                 │
│  GET  /api/best-time/{city}    → Open-Meteo weather                      │
│  GET  /api/geocode             → Nominatim proxy (en, is_country) ⭐UPD │
│  POST /api/compare-destinations→ 10-param AI comparison                  │
│  GET  /health                  → Readiness probe                          │
│                                                                            │
│  Security middleware (⭐ NEW v10.0):                                      │
│  - slowapi rate limiting: 10/min on all LLM-backed endpoints, 30/min      │
│    default elsewhere (IP-keyed, in-memory — single-instance only)        │
│  - CORS: allow_credentials=False, wildcard origin rejected by validator  │
│  - Structured JSON logging with PII redaction (core/logging_config.py)  │
│  - Prompt-injection guard (core/prompt_guard.py) wraps/neutralizes all   │
│    untrusted text (chat, scraped pages, RAG context) before LLM prompts │
│  - SSRF-hardened URL fetch in extract-trip (private-IP/metadata block)  │
│                                                                            │
│  Background (APScheduler):                                                │
│  - Reddit content refresh every 6h                                        │
│  - Qdrant vector ingestion on startup                                     │
└───────┬───────────────┬──────────────────┬────────────────────────────────┘
        │               │                  │
┌───────▼─────┐  ┌──────▼──────┐  ┌───────▼──────────────────────────────┐
│   Qdrant    │  │   Gemini    │  │  External APIs                        │
│ (in-memory) │  │  2.5 Flash  │  │                                        │
│             │  │  (primary)  │  │  • Nominatim/OSM  — geocoding         │
│ Collections │  │  lite / 1.5 │  │  • Open-Meteo    — weather            │
│  - reddit   │  │  fallbacks  │  │  • Reddit JSON   — travel tips        │
│  - wiki     │  │             │  │  • YouTube       — video thumbnails   │
└─────────────┘  └─────────────┘  │  • Wikipedia API — destination photos │
                                   │    (frontend, free, no key, CORS-safe)│
                                   │  • Pexels API    — optional itinerary  │
                                   │    day hero photos + attribution       │
                                   └───────────────────────────────────────┘

Embedding Model: sentence-transformers/all-MiniLM-L6-v2 (local, 384 dims)
```

---

## 2. Data Flow: LLM Anya Wizard

### 2.1 Overview

The wizard is fully LLM-powered. Each user message is sent to `POST /api/wizard-chat` (Gemini 2.5 Flash, temp 0.4). Anya returns a conversational reply, optional chip suggestions, a `config_patch` of newly extracted fields, and a server-computed `multi_select` boolean (⭐ v10.2 — tells the frontend whether the current chip group, e.g. travel themes, should allow picking several before continuing; replaces a fragile frontend keyword-matching heuristic that silently broke whenever Gemini phrased chip labels differently). The frontend merges patches into a local `partialConfig` state, tracks `_checkpoint_asked`, and shows progress pills for the 6 required fields. Assistant turns are JSON-wrapped with the real `config_patch` when replayed to Gemini so the model learns from the actual extraction history, not plain-text replies alone. The frontend now treats the backend's Stage-3 `summary` / `ready_to_generate` signal as the single source of truth for showing the generate CTA, so Stage-2 optional follow-up questions never strand the user without an input box.

Destination extraction now covers 4 cases in the system prompt (⭐ v10.2, was 3): single city, multiple explicitly-named places (**Case D** — first place becomes `destination`, the rest become `hops`), country-flexible (recommend me cities in a country, resolved to a real `destination`/`hops` the moment specific cities are named or confirmed — no longer left dangling in `destination_mode: "country"` with a blank city), and pure "surprise me" exploring mode.

**Edit mode (⭐ v10.2).** Reopening the wizard via "Edit Trip" on an already-generated itinerary is detected on mount (existing itinerary + a fully populated trip config, no fresh preload) and seeds `partialConfig` from the current config with `_checkpoint_asked: true` already set, instead of restarting Stage 1 from scratch. Anya greets with a one-line summary of the existing trip and offers "Change destination/dates/budget/themes" or "Regenerate as-is" chips. Stage-3 generate-signal trigger phrases were widened to also recognize "regenerate"/"update it" wording, which naturally comes up when editing rather than starting fresh.

```
openWizard() or openWizardWithPreload(preload)
         │
         ├─ If wizardPreload set → pre-populate partialConfig, send bootstrap message
         │
         ▼
STAGE 1 — Collect 6 required fields
LLMWizard.tsx → POST /api/wizard-chat
{
  messages: [{role, content, config_patch?}, ...],
  partial_config: { ...merged config + _checkpoint_asked flag },
  preloaded_destination: "Bali, Indonesia | null"
}
         │
         ▼
wizard_chat_chain.py
  ├─ System prompt v5: personality, Indian context, STT/Hinglish rules,
  │    6 required fields, 3-stage flow, config_patch rules, concrete MUST examples
  ├─ CURRENT_STATE summary injected (shows status: all-6-collected or checkpoint-asked)
  ├─ Assistant history replayed as JSON with real config_patch per turn
  ├─ Call Gemini 2.5 Flash (temp 0.4, max_tokens 2048)
  ├─ Validate full JSON via _looks_like_valid_json()
  ├─ Retry: 3 attempts with exponential backoff on 503/429/UNAVAILABLE
  │         and on successfully returned-but-incomplete JSON
  ├─ Smart mock fallback reads partial_config and asks next missing field
  ├─ Fallback reply cleanup: _strip_trailing_json_artifacts()
  └─ Parse JSON: { reply, chips, config_patch, ready_to_generate, summary }
         │
         ├─ Stage 1: ready_to_generate=false, missing fields → ask next question
         │
         ├─ Stage 2: all 6 fields present → Anya asks "anything else?" checkpoint
         │    → Frontend sets _checkpoint_asked=true in partialConfig
         │    → Chips: "Just generate it!", "Add themes", "Add departure city"
         │
         └─ Stage 3: checkpoint done + user confirms → ready_to_generate=true
              → frontend sees summary present and shows "Generate my itinerary" button
              → reply text is also trimmed with _strip_leaked_schema_tail() if Gemini echoed schema keys inside it
              → User clicks → merge partialConfig → streamItinerary → SSE
```

### 2.2 Required Fields

| # | Field | Example value |
|---|---|---|
| 1 | `purpose` | `"honeymoon"` |
| 2 | `destination` or `destination_mode` | `{city:"Bali", country:"Indonesia"}` or `"exploring"` |
| 3 | `dates` | `{start:"2026-09-01", end:"2026-09-08"}` or `{flexible:true, duration_days:7}` |
| 4 | `budget.amount` | `80000` (INR) |
| 5 | `group.adults` | `2` |
| 6 | `pace` | `"moderate"` |

### 2.3 Smart Extraction Examples

| User says | config_patch emitted |
|---|---|
| `"just me and my wife"` | `{group: {adults: 2, kids: [], seniors: 0, infants: 0, pets: 0}}` |
| `"₹1.5 lakh total"` | `{budget: {amount: 150000, currency: "INR"}}` |
| `"7 nights in September"` | `{dates: {start: "2026-09-01", end: "2026-09-07", flexible: false}}` |
| `"suggest me a destination"` | `{destination_mode: "exploring"}` |
| `"exploring Rajasthan"` | `{destination_mode: "country", destination_country: "India"}` |
| `"yaar Bali trip 7 days mein karo, budget 1.5L types"` | `{destination: {city:"Bali",...}, dates: {flexible:true, duration_days:7}, budget: {amount:150000,...}}` |
| `"araam se travel karna hai"` | `{pace: "relaxed"}` |
| `"family ke saath 4 log"` | `{group: {adults: 4,...}}` |
| `"Colombo, Mirissa, and Yala National Park"` (⭐ v10.2 Case D) | `{destination: {city:"Colombo",...}, hops: [{city:"Mirissa",...}, {city:"Yala National Park",...}]}` |
| `"Italy"` → Anya proposes Rome/Florence/Venice, user confirms (⭐ v10.2) | `{destination_mode: "fixed", destination: {city:"Rome",...}, hops: [{city:"Florence",...}, {city:"Venice",...}]}` |

### 2.4 Budget Recommendation & Pre-Generation Feasibility Gate (⭐ NEW v10.8 — UI/UX)

**Problem this fixes:** previously, if a user asked "what would this cost?" before group size was known, Anya quoted a flat, group-blind number straight from a parsing-only lookup table — and the LLM chat wizard never ran a feasibility check before auto-generating (only the older structured form did), so an unrealistic budget could sail straight into itinerary generation.

**New conversational UX (Stage 1, Field 4 — Budget):**
```
User: "What would a Maldives trip cost?"  (group size not yet known)
Anya: "Maldives for 6 days sounds wonderful! To give you a good idea
       of the cost, could you tell me who will be joining you?"
       chips: [Leisure 🌴, Adventure 🏔️, Honeymoon 💍, Family Vacation 👨‍👩‍👧, ...]
       (no budget number shown — Anya never guesses headcount)

User: "Me, my spouse, and our 3-year-old, mid-range comfort"
Anya: "For you, your spouse, and your little one, a comfortable
       mid-range trip for 6 days would be around ₹2,42,300 in total,
       about ₹80,800 per person. This covers flights, stay, and food.
       Activities/local transport/shopping would be extra."
       (real, destination-tier + season + group-aware number — no chip
        needed here, Anya just states it conversationally and continues
        to the next field)
```
This is powered server-side by `core/budget_estimator.py` (deterministic, no LLM cost math) — see `TECHNICAL_DOCUMENTATION.md` §14 v10.8. The frontend requires **no new UI component** for this part — it's the same chat bubble + chip pattern already used throughout the wizard; the difference is entirely in *what number Anya says and when*.

**New pre-generation feasibility gate (`LLMWizard.tsx`):** once Stage 3 (`ready_to_generate=true`) fires, the frontend now calls `POST /api/feasibility-check` (`runFeasibilityGate()`) **before** showing/starting the generate step:
```
              ┌─ feasible? ──────────────────────────────────────────┐
Stage 3 fires │                                                      │
ready_to_gen  ├─ YES → unchanged behaviour: 1.2s delay → handleGenerate()
= true        │
              └─ NO  → generation PAUSED. New assistant chat bubble:
                        "⚠️ Budget may be short by ₹X. Estimated
                         minimum is ₹Y (flights+stay+food floor).
                         Want to increase your budget, or shall I go
                         ahead with what you have?"
                        chips: ["Set budget to ₹Y", "Proceed anyway 🚀",
                                "Let me adjust something else"]
```
- **"Set budget to ₹Y"** — sends that as a normal chat message (Anya updates `budget.amount` via the usual `config_patch` flow, then Stage 3 re-fires and the gate re-checks).
- **"Proceed anyway 🚀"** — bypasses the LLM round-trip entirely; `handleSubmit()` special-cases this exact chip label to call `handleGenerate()` directly, so the user isn't stuck in a loop if they've deliberately chosen to travel on a tighter budget than recommended.
- **"Let me adjust something else"** — a normal chat message, keeps the conversation open (destination/dates/pace changes, etc.).
- **Fail-safe:** if the feasibility check call itself errors (network/server), the gate silently falls back to the original auto-generate behavior — an infra hiccup never blocks a user's trip.
- **Pre-booked costs:** if a user says they've already booked flights/a hotel (e.g. *"I already paid ₹50,000 for flights"*), Anya asks for the real total and stores it in `prebooked_flights_inr`/`prebooked_accommodation_inr` — the feasibility gate and any budget hint then use that real number instead of a heuristic guess for that line item.

**Destination comparison mode** also gains a new, non-LLM-guessed row: **"Estimated Trip Budget (bare minimum)"**, showing each candidate destination's real computed floor (e.g. *"Goa: ~₹44,000 total (₹22,000/person)"* vs *"Maldives: ~₹1,60,000 total (₹80,000/person)"*), with the cheaper destination highlighted as the winner — rendered by the existing generic comparison-row component, no new UI needed. The row is omitted entirely (not shown as "unknown") if group size hasn't been specified yet for the comparison.

### 2.5 Foreign-Currency Budget Input (⭐ NEW v10.9)

**Problem this fixes:** the wizard silently assumed every budget number was INR — never stated explicitly, and with no path for a user who naturally thinks in USD/EUR/etc. to state it in their own currency.

**Behavior now:**
- The **first time** Anya asks for budget, she explicitly says it's in ₹ (INR) and names the 10 supported alternative currencies: *"What's your approximate budget in ₹ (INR)? If you'd rather tell me in USD, EUR, GBP, AED, SGD, AUD, CAD, JPY, THB, or CHF, that's fine too — I'll convert it."*
- If the user's message contains a recognizable foreign-currency amount (`$2000`, `2000 USD`, `1500 euros`, `£1500`, `AED 5000`, `2k dollars`, etc.), `core/currency_convert.py::detect_foreign_currency()` extracts it via regex — deterministic, no LLM math involved.
- The amount is converted to INR via the free, keyless **Frankfurter.app** API (`convert_to_inr()`), cached in-memory for 6 hours, with a hardcoded approximate fallback rate table if the live call fails (never blocks the wizard on a network hiccup).
- The exact converted figure is injected into the prompt as a `{currency_conversion_hint}` (same pattern as the budget-estimator hint in §2.4) — Anya is instructed to use that number verbatim for `config_patch.budget.amount` (currency always stored as `"INR"`) and to state both figures + the rate transparently in her reply: *"Got it, $2,000 is about ₹1,73,000 at today's rate."*
- INR remains the sole canonical currency stored anywhere downstream (feasibility check, budget estimator, itinerary generation, scoring) — the conversion happens once, at the point of user input, so no other part of the system needs to be currency-aware.
- If a user mentions a currency outside the 10 supported ones, Anya asks them to restate in ₹ or one of the supported currencies rather than guessing.

Live-verified via curl: `"my budget is around $2000"` → `config_patch: {"budget": {"amount": 173000, "currency": "INR"}}`, reply mentions both the $2,000 and ₹1,73,000 figures.

---

## 3. Data Flow: Start Anywhere

```
User pastes URL or text into LandingHero input
         │
         ▼
handleStartAnywhere()
         │
         ├─ Empty input → openWizard() (plain)
         │
         └─ Has input → POST /api/extract-trip { input: string }
                │
                ▼
         Backend: extract_trip.py router
                │
                ├─ Starts with "http(s)://" ?
                │    └─ httpx.get(url) → strip HTML → first 6000 chars
                │
                └─ Extract trip text
                         │
                         ▼
                  Gemini 2.5 Flash (temp 0.1)
                  System: extraction schema
                  Output: ExtractedTrip JSON
                         │
                         ▼
              { destination, destination_country,
                duration_days, themes, budget_inr, summary }
                         │
         ◄───────────────┘
         │
         ├─ destination found →
         │    openWizardWithPreload({
         │      city: result.destination,
         │      country: result.destination_country,
         │      days: result.duration_days ?? 7,
         │      label: "City, Country"
         │    })
         │
         └─ no destination → openWizard() (plain fallback)
```

---

## 3A. Data Flow: Authentication (Signup / Login / Google SSO / Password Reset)

```mermaid
flowchart TD
    A["User hits auth surface<br/>/signup • /login • /forgot-password"] --> B{"Which path?"}

    B -->|Email signup| C["POST /api/auth/signup<br/>email + password + display_name + consent_accepted"]
    C --> C1["Argon2id hash password<br/>store consent_accepted + consent_accepted_at"]
    C1 --> C2["Set httpOnly cookies:<br/>wp_access_token + wp_refresh_token"]
    C2 --> C3["Frontend authStore becomes authenticated"]

    B -->|Email login| D["POST /api/auth/login"]
    D --> D1["Verify Argon2id password hash"]
    D1 --> C2

    B -->|Google SSO| E["GET /api/auth/google/start"]
    E --> E1["Sign stateless state param<br/>via itsdangerous serializer"]
    E1 --> E2["Redirect to Google consent screen"]
    E2 --> E3["GET /api/auth/google/callback?code=...&state=..."]
    E3 --> E4["Exchange code for tokens<br/>fetch /userinfo via httpx"]
    E4 --> E5["Upsert/find user by google_sub"]
    E5 --> C2

    B -->|Forgot password| F["POST /api/auth/password/forgot"]
    F --> F1["Always return 200<br/>even if email does not exist"]
    F1 --> F2["If account exists:<br/>create hashed single-use reset token<br/>send email via Resend"]
    F2 --> F3["User opens /reset-password?token=..."]
    F3 --> F4["POST /api/auth/password/reset"]
    F4 --> F5["Validate token TTL (~30 min)<br/>update Argon2id password hash<br/>revoke all refresh tokens"]

    C3 --> G["Future boot: AuthHydrator → GET /api/auth/me"]
    G --> H{"Access token valid?"}
    H -->|Yes| I["Hydrated session"]
    H -->|No| J["POST /api/auth/refresh"]
    J --> J1["Hash old opaque refresh token<br/>verify DB match<br/>rotate token pair"]
    J1 --> I
```

**Consent note:** signup is blocked unless the user accepts the linked Terms of Service and Privacy Policy. The checkbox is intentionally minimal in-page; the full legal text lives on dedicated `/terms` and `/privacy` pages.

**Nav auth indicator (⭐ NEW):** `components/common/UserMenu.tsx` renders "Log in"/"Sign up" when signed out, or the user's name/email + a "Log out" dropdown when signed in. Wired into `LandingHero`, `ThreeColumnLayout`, and `TopNav` — previously the app had no visible sign-in state anywhere outside `/account`.

---

## 3B. Data Flow: Account Deletion & Data Purge

```mermaid
flowchart TD
    A["Authenticated user opens /account"] --> B["Danger Zone UI requires typing DELETE"]
    B --> C["DELETE /api/auth/me"]
    C --> D["Delete users row"]
    D --> E["refresh_tokens.user_id ON DELETE CASCADE"]
    D --> F["password_reset_tokens.user_id ON DELETE CASCADE"]
    D --> G["events.user_id ON DELETE SET NULL"]
    G --> H["Aggregate analytics survive in anonymized form"]
    F --> I["Frontend clears auth state + returns to signed-out UX"]

    P["Admin bulk purge"] --> Q["Shipped & verified — /admin console Danger Zone"]
    Q --> R["Backend: DELETE /admin/users/{user_id}<br/>POST /admin/users/purge-all with confirmation string"]
    R --> S["Covered by integration tests; live-verified against dev server"]
```

---

## 3C. Data Flow: Admin Access Request & Approval

```mermaid
flowchart TD
    A["Signed-in non-admin opens /account"] --> B["Clicks 'Request admin access'<br/>(optional reason message)"]
    B --> C["POST /api/admin/requests"]
    C --> D{"Already admin?"}
    D -->|Yes| D1["400 — no request created"]
    D -->|No| E{"Existing pending request?"}
    E -->|Yes| E1["Return existing request unchanged<br/>(idempotent, no duplicate email)"]
    E -->|No| F["Create admin_requests row<br/>status = pending"]
    F --> G["Email every current admin<br/>(core/email.send_admin_request_notification,<br/>Resend; dev-log fallback if unset)"]
    G --> H["Requester sees 'pending review' on /account<br/>via GET /api/admin/requests/me"]

    I["Existing admin opens /admin"] --> J["GET /api/admin/requests?status=pending"]
    J --> K["Admin access requests panel<br/>lists name/email/message"]
    K --> L{"Admin decision"}
    L -->|Approve| M["POST /api/admin/requests/{id}/approve"]
    M --> M1["Set target user.is_admin = true"]
    M1 --> M2["status = approved, reviewed_by, reviewed_at"]
    M2 --> N["Email requester: approved<br/>(send_admin_request_decision_email)"]
    L -->|Reject| O["POST /api/admin/requests/{id}/reject"]
    O --> O1["is_admin unchanged<br/>status = rejected"]
    O1 --> N2["Email requester: rejected"]

    M2 --> P["Requester's next GET /api/auth/me<br/>reflects is_admin: true<br/>UserMenu now shows 'Admin console' link"]
```

**Why this exists:** `SignupRequest` never accepted `is_admin` and the DB column defaults `false`, so nobody could become an admin *by accident*. What was missing was a formal, auditable, two-party workflow for legitimately granting admin access post-launch — this closes that gap without any weakening of the original guarantee.

**Idempotency & one-shot guarantees:**
- Creating a request while one is already `pending` returns the existing row instead of creating a duplicate (prevents notification spam on double-click/refresh).
- Both `/approve` and `/reject` return 400 if the request's status is no longer `pending` (prevents double-review races).
- All admin/requester emails are best-effort (same pattern as password reset) — a Resend outage never blocks the actual request/approval logic.

---

## 4. Data Flow: Itinerary Generation with RAG

```
User clicks "Generate my itinerary 🚀" (LLMWizard)
         │
         ▼
LLMWizard → check authStore / pendingGeneration state
         │
         ├─ signed out → savePendingGeneration(fullConfig)
         │              → redirect to /signup?returnTo=/
         │              → after auth, restore pending config and resume
         │
         └─ signed in → merge partialConfig → tripConfigStore.updateConfig()
         │
         ▼
streamItinerary(fullConfig, ...)
         │
         ▼
POST /api/generate-itinerary { trip_config: TripConfig }
         │
         ▼
Depends(get_current_user)
         │
         ├─ no valid session → HTTP 401 (frontend maps to AUTH_REQUIRED)
         │
         └─ authenticated user →
         │
         ▼
itinerary_chain.py
         │
         ├─ CACHE CHECK (best-effort, non-blocking on success path) ──────
         │    itinerary_cache.py stores on success; consulted only in the
         │    failure/fallback branch below (see §15)
         │
         ├─ RAG RETRIEVAL ──────────────────────────────────────────────
         │    services/search.py → retrieve_context(trip_config, enable_reranking=True)
         │    │
         │    ├─ Build 3 query variants in parallel:
         │    │    Q1: "{city} travel {personas} highlights activities food"
         │    │    Q2: "things to do in {city} {purpose} {pace} hidden gems"  ── run through HyDE
         │    │    Q3: "{city} best restaurants sightseeing transport safety"
         │    │
         │    ├─ HyDE (services/hyde.py): Q2 is replaced with a synthesized
         │    │    hypothetical travel-guide passage before embedding — template-based,
         │    │    persona/pace/purpose aware, no extra LLM call/latency
         │    │
         │    ├─ asyncio.gather() → 3 × semantic_search(limit=15), each wrapped in
         │    │    asyncio.to_thread() so calls run on real worker threads (previously
         │    │    all serialized on the event loop — fixed this session)
         │    │    Each: hybrid search = BM25 (Qdrant scroll, destination-scoped) +
         │    │    embed(query) → 384-dim cosine search, fused via RRF
         │    │    Filter: destination == trip_config.destination.city
         │    │    Collections: wiki + reddit (split 50/50 per query)
         │    │
         │    ├─ _rrf_merge(): Reciprocal Rank Fusion (k=60)
         │    │    Score = Σ 1/(60 + rank_i) across 3 query lists
         │    │    Top-40 unique chunks kept for reranking
         │    │
         │    └─ Cross-encoder reranking (ms-marco-MiniLM-L-6-v2) — ONLY on this
         │         call site (itinerary generation). Scores (query, doc) pairs jointly;
         │         falls back to RRF order on any failure. Top-20 returned with published_date.
         │         Disabled by default elsewhere (settings.reranking_enabled=False) since a
         │         cross-encoder pass adds real latency (~23.6 → ~7 req/s @ concurrency=50
         │         when enabled globally) — scoping it here keeps other RAG callers fast.
         │
         ├─ RAG COMPRESSION ────────────────────────────────────────────
         │    summarise_context(context_docs, max_chars=2400)
         │    │
         │    ├─ Time-decay: score × (0.4 + 0.6 × 0.5^(age/548))
         │    │    e.g. 3yr-old post: 0.91 → 0.50, 1-month post: 0.91 → 0.89
         │    │
         │    ├─ Score filter: drop decayed < 0.35
         │    │
         │    ├─ Jaccard dedup: >60% word overlap → keep highest scored
         │    │
         │    ├─ Sort by decayed score DESC
         │    │
         │    └─ Truncate at 2400 chars (~600 tokens)
         │         was: ~30,000 chars (7,500 tokens) — 12× reduction
         │
         ├─ Assemble Gemini prompt:
         │    SYSTEM_PROMPT.format(
         │      context = summarised RAG context (≤600 tokens),
         │      trip_config = TripConfig JSON
         │    )
         │
         ├─ Retry loop (5 attempts):
         │    Model 1-3: gemini-2.5-flash (temp 0.4)
         │    Model 4:   gemini-2.5-flash-lite
         │    Model 5:   gemini-1.5-flash
         │    Each: validate JSON schema → ItineraryResponse
         │
         ├─ On success → store_itinerary() caches result (best-effort, strips
         │    any "_"-prefixed fallback markers so degraded output can never be cached)
         │
         ├─ Photo enrichment (best-effort): build one query per day as
         │    "{destination city or country} {day theme}" → services/pexels.py
         │    runs concurrent lookups via get_day_photos() under a 6s overall timeout
         │    and patches ItineraryDay.image_url, image_photographer,
         │    image_photographer_url when available
         │
         ├─ On exception (all retries + Groq/Ollama exhausted) → _fallback_itinerary()
         │    3-tier chain: cache hit → OSM-grounded skeleton → RAG-tipped mock (see §15)
         │
         ◄─ SSE stream: status events → final ItineraryResponse
         │
         ▼
itineraryStore.setDays(days, score, breakdown)
closeWizard() → render ThreeColumnLayout
```

---

## 5. Data Flow: Persistent Anya Chat

```
User clicks FloatingAnyaButton (shown when itinerary exists)
         │
         ▼
useChatStore.open() → ChatPanel renders (fixed bottom-right, 360px wide)
         │
         ▼
User types message + sends
         │
         ▼
POST /api/chat-refine {
  messages: [...history],
  trip_config: tripConfigStore.config
}
         │
         ▼
chat_refine_chain.py
         │
         ├─ Gemini 2.5 Flash
         │    System: "You are Anya... CURRENT TRIP CONFIG: {config_json}"
         │    User: conversation history
         │
         └─ Output: { reply, action_type, config_patch, major_change }
         │
         ◄─ response
         │
         ├─ action_type = 'none'
         │    → display reply in ChatPanel
         │
         ├─ action_type = 'patch_config'
         │    → updateConfig(config_patch) silently
         │    → display reply ("I've updated your budget to ₹1.5L!")
         │
         └─ action_type = 'regenerate' + major_change = true
              → show confirmation dialog in ChatPanel:
                   ┌─────────────────────────────────┐
                   │ ⚠️ This change will regenerate  │
                   │ [Yes, apply & reset] [Just noting]│
                   └─────────────────────────────────┘
              ├─ "Yes" → updateConfig + resetItinerary
              └─ "Just noting it" → dismiss, no action
```

---

## 6. Data Flow: Share Trip Link

```
User clicks ShareButton (center column header)
         │
         ├─ shareUrl already cached → copy to clipboard → show "Link copied!"
         │
         └─ First click:
                  │
                  ▼
         POST /api/share {
           itinerary: { days, alignment_score, expense_breakdown },
           trip_config: tripConfigStore.config,
           labels: wizardChatStore.collectedLabels,
           destination_label: "Bali, Indonesia"
         }
                  │
                  ▼
         share.py router (rate-limited 10/min per IP)
           → slug = secrets.token_urlsafe(16)   e.g. "bS6AneQqDEye_NRSjOFCpg" (128-bit, ⭐ UPD v10.0)
           → _store[slug] = payload
           → return { slug, url: "/t/bS6AneQqDEye_NRSjOFCpg" }
                  │
                  ◄──────
                  │
         navigator.clipboard.writeText(origin + url)
         setShareUrl(url)  ← cache for subsequent clicks
         Button: "Link copied!" (green, 3s)

Recipient opens https://wanderplanner.app/t/a1b2c3d4
         │
         ▼
app/t/[slug]/page.tsx
         │
         ▼
GET /api/share/bS6AneQqDEye_NRSjOFCpg
         │
         ├─ Found → { itinerary, trip_config, labels, destination_label }
         │    → render read-only day-by-day view
         │    → "👁 View-only" badge
         │    → "Plan my own trip →" CTA
         │
         └─ Not found → error state ("This trip link has expired or doesn't exist.")

Note: In-memory store resets on server restart.
      Production: swap _store for Redis or a database.
```

---

## 7. Data Flow: Voice Interaction

```
User clicks voice icon in wizard header
         │
         ▼
setVoiceModeActive(true) → ListeningOrb animates
         │
         ▼
SpeechRecognition.start()
  lang: 'en-IN'
  continuous: false
  interimResults: true
         │
User speaks → transcription fills input field in real-time
         │
         ▼
SpeechRecognition 'result' event (isFinal=true)
         │
         ▼
handleSubmit(transcript) → normal wizard message flow
         │
         ▼
Latest bot reply → SpeechSynthesis.speak(utterance)
  voice: first 'en-IN' female voice found in getVoices()
  rate: 0.9, pitch: 1.1, volume: 1.0
```

---

## 8. API Contract

### Request / Response Schemas

#### `POST /api/wizard-chat` ⭐ NEW
```
Request:  {
  messages: [{role:'user'|'assistant', content:string, config_patch?: object}],
  partial_config: Partial<TripConfig>,
  preloaded_destination: string | null
}
Response: {
  reply: string,
  chips: string[],
  config_patch: Partial<TripConfig>,
  ready_to_generate: bool,
  summary: string | null
}
```

#### `POST /api/generate-itinerary`
```
Request:  { trip_config: TripConfig }
Response: SSE stream
  event: status  → { message: string, step: int, total: int }
  event: result  → ItineraryResponse
  event: error   → { code: string, message: string, retryable: bool }

ItineraryResponse:
  { days: ItineraryDay[], alignment_score: int, expense_breakdown: ExpenseBreakdown }

ItineraryDay:
  { day_number: int, date: string, theme: string,
    items: ItineraryItem[], transit_warnings: TransitWarning[],
    image_url?: string, image_photographer?: string, image_photographer_url?: string }

ItineraryItem:
  { id, time_start, time_end, title, local_name?, description,
    location: { lat, lon, address, place_name },
    tags, booking_url, youtube_video_id, alignment_score, warnings }
```

#### `POST /api/chat-refine`
```
Request:  { messages: [{role:'user'|'assistant', content:string}], trip_config: TripConfig }
Response: { reply: string, action_type: 'none'|'patch_config'|'regenerate',
            config_patch: Partial<TripConfig>|null, major_change: bool }
```

#### `POST /api/extract-trip` ⭐ NEW
```
Request:  { input: string }   // URL or free-form text
Response: { destination: string|null, destination_country: string|null,
            duration_days: int|null, themes: string[], budget_inr: int|null,
            summary: string }
```

#### `POST /api/share` ⭐ NEW
```
Request:  { itinerary: object, trip_config: object,
            labels: Record<string,string>, destination_label: string }
Response: { slug: string, url: string }
```
Rate-limited 10/min per IP. Slug is `secrets.token_urlsafe(16)` (128-bit, ⭐ UPD v10.0 — was `uuid4().hex[:8]`).

#### `GET /api/share/{slug}` ⭐ NEW
```
Response: same shape as POST /api/share body, or 404
```
Rate-limited 10/min per IP.

#### `GET /api/geocode?q={query}`
```
Response: { display_name: string, lat: float, lon: float,
            country_code: string, is_country: bool }
```
`is_country=true` when Nominatim resolves the query to a country-level boundary
(no city/town/village/municipality in address; only country).

#### `POST /api/recommend-cities`
```
Request:  { country: string, trip_config: TripConfig }
Response: { cities: [{ name, country, lat, lon, tagline }] }
```

#### `POST /api/compare-destinations`
```
Request:  { destinations: string[], trip_config: TripConfig }
Response: ComparisonResponse (10 params × N destinations)
Parameters: budget_fit, weather, visa_ease, family_fit, romance, food_scene,
            adventure, safety, unique_experiences, overall_score
```

#### `GET /api/travel-tips?destination={city}`
```
Response: { tips: TravelTip[], reddit_highlights: RedditHighlight[] }
Cached: 1 hour per destination
```

#### `GET /api/best-time/{city}`
```
Response: { best_months: string[], weather_summary: string, avoid_months: string[],
            events: [{name, month, description}] }
```

---

## 8A. Database Schema

The app now uses **Postgres** (Supabase in production) for user/auth/analytics state. This is separate from **Qdrant**, which remains the vector database for RAG retrieval.

### Production setup runbook (⭐ NEW v10.10 — Supabase Postgres)

1. **Create a free Supabase project** (supabase.com → New Project). Free tier: 500MB database, 2GB bandwidth/month, up to 60 concurrent direct connections — sufficient for this app's traffic today.
2. **Copy the pooled connection string**, not the direct one: Project Settings → Database → "Transaction pooler" (port `6543`, PgBouncer-backed). Railway's short-lived request-scoped connections can exhaust Supabase's free-tier direct-connection cap (60) under concurrent load; the pooler avoids that.
3. **Set two Railway env vars**:
   - `DATABASE_URL=postgresql+asyncpg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres`
   - `DATABASE_SSL_REQUIRE=true` — Supabase requires TLS on every connection; `asyncpg` does **not** negotiate SSL automatically from a bare connection string, so this is a genuine footgun without the explicit flag (`db.py` passes `connect_args={"ssl": True}` only when this is set).
4. **Migrations now run automatically on every deploy** (⭐ fixed this pass): `railway.toml`'s `startCommand` was `uvicorn ...` only — a fresh Supabase database would have booted with **no tables at all** until someone manually ran `alembic upgrade head`. It's now `alembic upgrade head && uvicorn ...`, so every deploy is guaranteed to be on the latest schema.
5. **Local SQLite dev now matches Postgres migrations exactly** (⭐ fixed this pass): migration `0001_auth_analytics.py` hardcoded `postgresql.JSONB()` for `events.event_metadata` with no SQLite fallback, so `alembic upgrade head` against a *fresh* local SQLite database (the exact command CI/new-contributor onboarding would run) crashed with `CompileError: can't render element of type JSONB` the moment it reached the `events` table — the ORM model (`db_models/event.py`) already correctly used `JSONB().with_variant(JSON(), "sqlite")`, but the raw migration script hadn't matched it. Fixed by adding the same `.with_variant(sa.JSON(), "sqlite")` to the migration. Verified: `alembic upgrade head` now runs cleanly end-to-end (`0001` → `0002` → `0003`) against a brand-new SQLite file.
6. **Free-tier pause caveat**: Supabase free projects auto-pause after 7 days with zero database activity and need a manual "Resume" click from the dashboard (or any query keeps it warm) — a real caveat for demo days after a quiet week, not a bug.

### `users`

| Column | Notes |
|---|---|
| `id` | UUID primary key |
| `email` | Unique email login identifier |
| `password_hash` | Argon2id hash; nullable for Google-first accounts |
| `display_name` | Optional profile name |
| `auth_provider` | `password` or `google` |
| `google_sub` | Unique Google subject for SSO accounts |
| `is_admin` | Admin-dashboard access gate |
| `consent_accepted` | Required signup consent flag |
| `consent_accepted_at` | Timestamp of captured consent |
| `created_at` | Account creation timestamp |

### `refresh_tokens`

| Column | Notes |
|---|---|
| `id` | UUID primary key |
| `user_id` | FK → `users.id`, `ON DELETE CASCADE` |
| `token_hash` | SHA-256 of opaque refresh token |
| `expires_at` | Refresh-token expiry |
| `created_at` | Issued timestamp |

Refresh tokens rotate on every `/api/auth/refresh` call; only the hash is stored server-side.

### `events`

| Column | Notes |
|---|---|
| `id` | UUID primary key |
| `event_type` | Generic analytics event name |
| `event_metadata` | JSONB payload for event-specific detail |
| `user_id` | Nullable FK → `users.id`, `ON DELETE SET NULL` |
| `created_at` | Indexed event timestamp |

The generic `event_type + JSONB metadata` design intentionally avoids new migrations for every analytics/cost-tracking addition.

### `password_reset_tokens`

| Column | Notes |
|---|---|
| `id` | UUID primary key |
| `user_id` | FK → `users.id`, `ON DELETE CASCADE` |
| `token_hash` | SHA-256 of raw reset token |
| `expires_at` | ~30 minute TTL |
| `used_at` | Single-use marker |
| `created_at` | Issued timestamp |

### `admin_requests` (⭐ NEW)

| Column | Notes |
|---|---|
| `id` | UUID primary key |
| `user_id` | FK → `users.id`, `ON DELETE CASCADE` — the requester |
| `status` | `pending` \| `approved` \| `rejected`; indexed |
| `message` | Optional free-text reason from the requester |
| `reviewed_by` | Nullable FK → `users.id`, `ON DELETE SET NULL` — the admin who approved/rejected |
| `reviewed_at` | Timestamp of decision, null while pending |
| `created_at` | Request creation timestamp |

Enforces the "no auto-admin" policy: `is_admin` is only ever flipped `true` via the `/admin/requests/{id}/approve` endpoint (or an out-of-band DB seed for the very first admin) — never by the signup flow itself.

Migrations:
- `0001_auth_analytics`
- `0002_password_reset`
- `0003_admin_requests`

---

## 9. Qdrant Collection Schema

Four active collections, all using `all-MiniLM-L6-v2` (384 dims, cosine distance):

### `reddit` collection
```json
{
  "vector": [384 floats],
  "payload": {
    "text": "Title prefix + paragraph chunk (≥80 chars)",
    "title": "Original Reddit post title",
    "destination": "Bali",
    "subreddit": "solotravel",
    "reddit_score": 142,
    "published_date": "2026-05-12",
    "post_url": "https://reddit.com/r/...",
    "text_preview": "First 300 chars of chunk"
  }
}
```
**Chunking:** Each post → N paragraph chunks (`\n\n` split, ≥80 chars). Each chunk is prefixed with the post title for standalone retrieval context. Point ID: `md5(post_url + text[:50])`.

### `wiki` collection
```json
{
  "vector": [384 floats],
  "payload": {
    "text": "Sentence-boundary chunk (~500 chars)",
    "destination": "Bali",
    "section": "see",
    "source_url": "https://en.wikivoyage.org/..."
  }
}
```
**Chunking:** Each Wikivoyage section → N sentence-boundary chunks (~500 chars, ≥80 chars min). Point ID: `md5(url + section + text[:50])`.

### `osm_pois` collection ✅ Live (weekly ingestion)
```json
{
  "vector": [384 floats],
  "payload": {
    "text": "Short embeddable description, e.g. 'Tanah Lot Temple — temple in Bali'",
    "name": "Tanah Lot Temple",
    "type": "temple",
    "lat": -8.6212,
    "lon": 115.0868,
    "destination": "Bali",
    "tags": ["tourism=attraction", "historic=temple"]
  }
}
```
Populated by `scrapers/osm.py::ingest_osm_pois()` from the free Overpass API (no key required); geocodes the destination, queries a ~5km radius across ~14 POI tag categories, dedupes by name. Consumed today by the Tier-2 RAG-skeleton fallback (§15); direct itinerary-grounding is a planned next step (see `docs/rag-strategy.md` §6, use case #1).

### `itinerary_cache` collection ✅ Live (populated organically on successful generations)
```json
{
  "vector": [384 floats],
  "payload": {
    "destination": "Bali",
    "duration_days": 5,
    "pace": "moderate",
    "purpose": "leisure",
    "itinerary_json": "{...serialized ItineraryResponse...}",
    "generated_at": "2026-07-02T10:00:00Z"
  }
}
```
Key: `embed(f"{destination} {duration_days}d {pace} {purpose} trip")`. Written by `services/itinerary_cache.py::store_itinerary()` after every successful LLM generation (best-effort, never blocks the response; strips any `_`-prefixed fallback markers so degraded fallback output is never cached). Read by `get_cached_itinerary()` with `score_threshold=0.88` as Tier 1 of the fallback chain.

### Ingestion Schedule
- **Reddit**: APScheduler, every 6h. Subreddits: `travel`, `solotravel`, `digitalnomad`, `backpacking`.
- **Wiki**: On-demand, triggered at itinerary generation time for the destination if not cached.
- **OSM POIs**: APScheduler, weekly (`osm_refresh_days` setting). Iterates `KNOWN_DESTINATIONS` with a polite delay (`osm_ingest_delay_seconds`) between Overpass calls.
- **Itinerary cache**: Event-driven — written on every successful itinerary generation, no separate scheduled job.

---

## 9A. Admin Analytics & Cost Tracking

### Access-control model

All admin metrics routes depend on `get_current_admin_user`:

- unauthenticated caller → **401**
- authenticated non-admin caller → **403**
- authenticated admin caller → success

The 403 branch is intentional so the frontend can distinguish "sign in first" from "you're signed in but not authorized."

### Metrics endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/admin/metrics/summary` | Aggregate counts for users, signups, sessions, logins, itinerary outcomes, and cost/usage buckets |
| `GET /api/admin/metrics/timeseries?range=7d|30d` | Daily event counts grouped by `event_type` |
| `POST /api/analytics/client-event` | Browser-originated beacons such as `session_start` and YouTube-thumbnail events |

### Event design

The `events` table is append-only and generic. Current event families include:
- `signup`
- `login_success`
- `login_failed`
- `session_start`
- `itinerary_generated`
- `itinerary_failed`
- allowlisted client-originated YouTube thumbnail events

### Cost-tracking status

The backend summary endpoint already exposes fields for:
- Gemini call counts
- Gemini token totals
- Gemini estimated USD cost
- Pexels call counts

However, **Gemini token/cost event instrumentation is still in progress** in the verified backend code path. Document this as a prepared monitoring surface rather than a fully populated production dashboard today. The intended scope covers all Gemini call sites plus free-tier-aware tracking for Pexels and client-side YouTube thumbnail fetches.

---

## 10. Gemini Prompt Design & Temperature Settings

### Model & Temperature Reference

| Endpoint | Chain file | Model | Temperature | Max tokens |
|---|---|---|---|---|
| `POST /api/wizard-chat` | `wizard_chat_chain.py` | `gemini-2.5-flash` | **0.4** | 2048 |
| `POST /api/chat-refine` | `chat_refine_chain.py` | `gemini-2.5-flash` | **0.5** | 1024 |
| `POST /api/generate-itinerary` (attempts 1-3) | `itinerary_chain.py` | `gemini-2.5-flash` | **0.4** | 16384 |
| `POST /api/generate-itinerary` (attempt 4) | `itinerary_chain.py` | `gemini-2.5-flash-lite` | **0.4** | — |
| `POST /api/generate-itinerary` (attempt 5) | `itinerary_chain.py` | `gemini-1.5-flash` | **0.4** | — |
| `POST /api/extract-trip` | `extract_trip_chain.py` | `gemini-2.5-flash` | **0.1** | 512 |
| `POST /api/recommend-cities` | `recommend_cities_chain.py` | `gemini-2.5-flash` | **0.4** | 1024 |

Temperature rationale:
- **0.4** — Wizard: more deterministic extraction while keeping Anya conversational
- **0.5** — Chat refine: friendly but semi-deterministic for config patches
- **0.4** — Itinerary/cities: structured JSON; lower = fewer schema violations
- **0.1** — Extraction: near-deterministic; wrong extraction = wrong wizard preload

---

### System Prompt 1 — Anya Wizard (`wizard_chat_chain.py`)

**Version:** v5 (June 2026) — end-to-end extraction fix, JSON history replay, stricter patch behavior

**Key sections:**
- **System Purpose** — Anya is defined as a human travel professional speaking to a customer, not a slot-filling agent. Explicitly states she never narrates internal logic.
- **Persona & Tone** — warm Indian travel expert friend; 2-3 sentences max; TTS-optimised
- **Absolute Speaking Rules (§1a)** — hard prohibition on field names, system terms (`config_patch`, `destination_mode`, `missing field`), and internal reasoning in `reply`. Includes three verbatim WRONG/RIGHT examples from real failure cases.
- **Indian Cultural Context** — currency parsing (25k→25000, 1L→100000), travel seasons (Oct-Nov Diwali, Apr-May school holidays), joint family norms, veg/Jain food sensitivity
- **Audio/STT Handling** — Hinglish glossary (araam se→relaxed, family ke saath→family, bas karo→generate), filler word stripping, number speech (seven days→7)
- **6 Required Fields** — each with JSON key, valid values, and explicit phrase mappings
- **Optional Fields** — auto-inferred themes (honeymoon→wellness, adventure purpose→adventure)
- **Slot Filling** — never re-ask collected fields; defaults for "surprise me" (leisure, 6 days, 1L, moderate)
- **3-Stage Flow** — Stage 1: collect 6 fields → Stage 2: "anything else?" checkpoint → Stage 3: generate signal
- **config_patch Rules** — "include every extracted field even if you think it is already known" and `config_patch` must never be empty when the user just supplied usable trip info
- **JSON-Wrapped History** — assistant turns are replayed as JSON objects like `{"reply":"...","config_patch":{...}}` so Gemini learns from the real extraction history
- **Retry Logic** — 3 attempts with exponential backoff on 503/429/UNAVAILABLE, plus parse-based retries when `_looks_like_valid_json()` detects a truncated/incomplete JSON body
- **Fallback Text Sanitisation** — `_strip_trailing_json_artifacts()` removes dangling JSON punctuation from salvage text, while `_strip_leaked_schema_tail()` trims escaped schema-key echoes from the `reply` field itself
- **Smart Mock Fallback** — reads `partial_config` and asks the next missing required field instead of returning a generic fallback
- **Filled-State Consistency** — frontend `allFilled` is unified with `_isFieldFilled`, matching the progress pill logic
- **Output Schema** — JSON only; `reply` is described as "what Anya says on a phone call — no field names, no system terms, no internal reasoning"

The backend `_has_all_required()` server-validates `ready_to_generate`. Stage 2 checkpoint is tracked via `_checkpoint_asked` flag in `partialConfig` and surfaced to the LLM via `CURRENT_STATE`. Assistant history also includes raw-JSON leak guards (`or raw` → `or ""`) plus double-wrapped JSON detection before replay. A `_strip_leaked_reasoning()` function remains the last-resort safety net, but most user-visible truncation issues are now intercepted earlier by JSON completeness checks and the two cleanup helpers above.

---

### System Prompt 2 — Anya Post-Gen Chat (`chat_refine_chain.py`)

```
You are Anya, WanderPlanner's friendly AI travel assistant.

CURRENT TRIP CONFIG: {trip_config_json}

RESPONSE FORMAT:
{
  "reply": "...",
  "action_type": "none" | "patch_config" | "regenerate",
  "config_patch": null or { ...changed fields... },
  "major_change": false
}

- patch_config: small changes (pace, themes, accommodation)
- regenerate: destination/dates/group/budget >20% → ask user to confirm
```

---

### System Prompt 3 — Itinerary Generation (`itinerary_chain.py`)

```
You are WanderPlanner, an expert AI travel advisor.
Output ONLY valid JSON matching the schema.

RULES:
- 3-6 items/day  •  relaxed=3-4  •  moderate=4-5  •  packed=5-6
- If kids: exclude bars, nightclubs, extreme sports
- If digital_nomad: add 2h Work Block per day
- If sports_fitness: add Training Window per day
- Tag photogenic spots with "instaworthy"
- MULTI-HOP: distribute days across all stops proportionally

DESTINATION RESEARCH: {context}    ← RAG-retrieved Qdrant chunks
TRIP CONFIGURATION:   {trip_config}
```

---

### System Prompt 4 — Extract Trip (`extract_trip_chain.py`)

```
You are a travel data extraction assistant. Extract structured trip info.
Return ONLY valid JSON:
{
  "destination": "City or null",
  "destination_country": "Country or null",
  "duration_days": int or null,
  "themes": ["list"],
  "budget_inr": int or null,
  "summary": "One sentence."
}
```
Temperature: 0.1 (deterministic) · Max tokens: 512

---

## 11. Frontend State Architecture

### Store Dependency Graph

```
appStore
  └── wizardPreload → consumed by LLMWizard on open

tripConfigStore
  └── config → consumed by: LLMWizard (on generate), itinerary chain, chat-refine, shareTrip, ShareButton

wizardChatStore
  ├── messages → rendered by LLMWizard (legacy: ConversationalWizard)
  ├── currentField → legacy field tracking
  └── collectedLabels → passed to shareTrip
     readyToGenerate in the live wizard is derived from backend `summary` state,
     not a frontend required-field counter, so Stage-2 follow-up turns stay interactive

itineraryStore
  ├── days → consumed by: ThreeColumnLayout, ItineraryTimeline, MapWrapper, ShareButton
  ├── activeDay → drives day-tab selection, map center
  └── expenseBreakdown → ExpenseBreakupCard

chatStore
  ├── isOpen → ChatPanel visibility
  └── messages → ChatPanel message history

bookingStore (persisted)
  └── bookings → BookingHub display + localStorage
```

### Key State Transitions

```
Landing page (no itinerary):
  LandingHero shown
  FloatingAnyaButton: hidden
  ChatPanel: hidden

Wizard open (no itinerary):
  LandingHero blurred/dimmed
  LLMWizard overlay shown (LLM-powered Anya)
  FloatingAnyaButton: hidden

Itinerary exists, wizard closed:
  ThreeColumnLayout shown
  FloatingAnyaButton: visible → click → chatStore.open()
  ChatPanel: visible when chatStore.isOpen

Itinerary exists, wizard open (edit flow):
  ThreeColumnLayout blurred/dimmed
  LLMWizard overlay shown
  ChatPanel: hidden (wizard takes precedence)

Full-screen map (step3View = 'map-full'):
  ThreeColumnLayout renders full-height MapWrapper
  Day-tab toolbar replaces column headers
  "Close map" → step3View = 'itinerary'
```

---

## 12. Design System

### Color Tokens

| Token | Light | Dark | Usage |
|---|---|---|---|
| `--_primary` | `#0EA5E9` | `#38BDF8` | CTAs, links, active states |
| `--_accent` | `#EA580C` | `#FB923C` | Hero CTA button |
| `--_ocean` | `#0C4A6E` | `#0C4A6E` | Headings |
| `--_bg` | `#F8FAFC` | `#0B1120` | Page background |
| `--_card` | `#FFFFFF` | `#111827` | Card surfaces |
| `--_card-elevated` | `#F1F5F9` | `#1E293B` | Elevated cards |
| `--_fg` | `#0F172A` | `#F1F5F9` | Primary text |
| `--_muted-fg` | `#64748B` | `#94A3B8` | Secondary text |
| `--_border` | `#E2E8F0` | `#1E293B` | Borders, dividers |

### CSS Specificity Note
`.input` class in `globals.css` sets `padding: 0.625rem 0.875rem`.
To override inline padding (e.g. icon-padded inputs), use `style={{ paddingLeft: '...' }}` (inline style beats class).

### Scrollable Column Chain
For `overflow-y-auto` to activate on column children:
```
div.h-screen.flex.flex-col   →  div.flex-1.overflow-hidden
→  main.h-full  →  ThreeColumnLayout  →  aside.overflow-y-auto
```
Breaking any link in this chain prevents scrolling. `<main className="h-full">` is critical.

### Component Conventions
- Design tokens via `var(--_*)` CSS custom properties — never hardcode hex colors
- Dark mode: all components use tokens; no Tailwind `dark:` prefixes needed
- `cn()` or direct Tailwind classname concatenation with `[].join(' ')`
- Lucide icons for all UI iconography (consistent 13–18px sizes in UI chrome)

---

## 13. Environment Variables Reference

### Backend (`apps/api/.env`)

| Variable | Default | Required | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | — | ✅ | Google Gemini API key |
| `LLM_PROVIDER` | `gemini` | — | `gemini` or `mock` (for testing) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | — | Primary model ID |
| `DATABASE_URL` | — | ✅ | Postgres connection string (local Postgres or Supabase) |
| `JWT_SECRET` | — | ✅ | Secret for signing access tokens and auth state |
| `ACCESS_TOKEN_TTL_MINUTES` | `15` | — | Access-token lifetime |
| `REFRESH_TOKEN_TTL_DAYS` | `30` | — | Refresh-token lifetime |
| `COOKIE_DOMAIN` | `""` | — | Optional cookie domain override |
| `COOKIE_SECURE` | `true` | — | Must be `true` in production for cross-origin cookies |
| `COOKIE_SAMESITE` | `lax` | — | Use `lax` locally, `none` in cross-origin production |
| `GOOGLE_CLIENT_ID` | — | ✅ for SSO | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | — | ✅ for SSO | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8000/api/auth/google/callback` | ✅ for SSO | OAuth callback URI |
| `FRONTEND_BASE_URL` | `http://localhost:3000` | ✅ | Redirect target after auth/password flows |
| `RESEND_API_KEY` | — | ✅ for password reset | Resend HTTP API key |
| `EMAIL_FROM_ADDRESS` | `Wanderplanner <no-reply@wanderplanner.app>` | — | Password-reset sender |
| `PASSWORD_RESET_TOKEN_TTL_MINUTES` | `30` | — | Reset-link expiration |
| `QDRANT_URL` | `:memory:` | — | Qdrant instance URL |
| `ALLOWED_ORIGINS` | `["http://localhost:3000"]` | ✅ | CORS whitelist — **must be JSON-array format** (pydantic-settings list parsing), `"*"` is rejected by a validator (⭐ NEW v10.0) |
| `PEXELS_API_KEY` | — | — | Optional Pexels API key for itinerary day hero photos; generation degrades gracefully without it |
| `LOG_LEVEL` | `INFO` | — | Structured JSON logging level (⭐ NEW v10.0, `core/logging_config.py`) |
| `NOMINATIM_USER_AGENT` | `wanderplanner/1.0` | — | Nominatim ToS compliance |
| `NOMINATIM_RATE_LIMIT` | `1` | — | Requests per second |

### Frontend (`apps/web/.env.local`)

| Variable | Default | Required | Description |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | ✅ | Backend base URL |
| `NEXT_PUBLIC_MAPTILER_KEY` | — | — | MapTiler key (optional, default OSM tiles work) |

---

## 14. Performance & Cost Analysis

### Latency Targets

| Operation | Target | Actual (p95) |
|---|---|---|
| Wizard chat turn (LLM Anya) | < 4s | ~2–3s |
| Geocode (Nominatim, cached) | < 200ms | ~50ms (cache hit) |
| City recommendations | < 3s | ~2s |
| Trip extraction (Start Anywhere) | < 5s | ~3s |
| Itinerary generation | < 45s | ~25–35s |
| Chat refine response | < 8s | ~4s |
| Travel tips (cached) | < 200ms | ~50ms (cache hit) |

### Monthly Cost (100 active users)

| Service | Cost |
|---|---|
| Gemini 2.5 Flash (itinerary + chat + tips + extraction) | ~₹15–30 |
| Nominatim, Open-Meteo, Reddit, OSM, Wikipedia | Free |
| Vercel (frontend) | Free tier |
| Railway (backend) | Free tier ($5 credit covers ~10M req) |
| **Total** | **~₹15–30/month** |

Per-user cost: ~₹0.15–0.30

### Cost observability

In addition to static modeling, the new auth/analytics layer introduces an **events-backed cost monitoring path**:

- admin summary fields for Gemini call count / token totals / estimated USD cost
- Pexels call-volume tracking
- client-side YouTube thumbnail beacon events for calls the FastAPI backend does not directly observe

This is a **monitoring capability**, not a direct cost-reduction mechanism. The Gemini token/cost event instrumentation is still being completed end-to-end, so treat the dashboard fields as partly in progress rather than fully populated today.

### Caching Strategy

| Resource | Cache Type | TTL |
|---|---|---|
| Geocode results | LRU (Python, `lru_cache`) | Process lifetime |
| Travel tips | In-process dict | 1 hour per destination |
| Wikipedia images | Module-level Map (JS) | Session lifetime |
| YouTube thumbnails | Module-level Map (JS) | Session lifetime |
| Share slugs | In-memory dict (Python) | Server process lifetime |
| Pexels day-photo searches | In-memory dict (Python, max 500 query keys) | Server process lifetime |

---

## 15. Resilience & Retry Architecture

### Itinerary Generation Retry Chain

```
Attempt 1: gemini-2.5-flash, temperature=0.7
  → JSON parse failure or schema mismatch?
Attempt 2: gemini-2.5-flash, temperature=0.5 (slightly more deterministic)
  → Still failing?
Attempt 3: gemini-2.5-flash, temperature=0.3
  → Still failing?
Attempt 4: gemini-2.5-flash-lite (simpler, faster, cheaper)
  → Still failing?
Attempt 5: gemini-1.5-flash (stable fallback)
  → All fail → RAG-powered 3-tier fallback (✅ new this cycle, replaces the old
     bare SSE-error behaviour):
       Tier 1: itinerary_cache lookup (cosine ≥ 0.88) → instant cached itinerary
       Tier 2: rag_skeleton_itinerary() — real OSM POIs slotted into day structure,
                requires ≥3 POIs ingested for the destination, else falls through
       Tier 3: _mock_itinerary(tip_texts=...) — static mock enhanced with real
                retrieved wiki/reddit snippets spliced in as "Local tip: ..."
                (always succeeds — final safety net)
```

### Extract Trip Resilience

```
3 attempts with 1s back-off between each.
All fail → return ExtractedTrip with all nulls + summary "Could not extract..."
Frontend fallback: openWizard() (plain, no preload)
```

### Wizard Chat Resilience

```
Attempt 1-3: Gemini 2.5 Flash (max_output_tokens=2048)
  → Transport error / 429 / 503 / timeout? retry with backoff
  → Response arrived but _looks_like_valid_json() says incomplete/truncated? retry too
All retries fail → smart mock fallback picks the next missing required field
Any salvage text shown to users is first cleaned by _strip_trailing_json_artifacts()
Valid JSON whose reply text contains an escaped schema echo is trimmed by
_strip_leaked_schema_tail() before rendering
```

### Wikipedia Image Resilience

```
useWikiImage(city) fetch fails → cache.set(key, null) → return null
Component: shows gradient fallback permanently (no retry loop)
```

### Chat Refine Resilience

```
POST /api/chat-refine fails →
  updateLastAssistant("Sorry, I couldn't connect right now. Please try again.")
  setStatus('error', 'Connection failed')
  Error banner shown in ChatPanel header
```

### Pexels Photo Resilience

```
PEXELS_API_KEY missing / request fails / no result / 6s itinerary photo budget exceeded
  → services/pexels.py returns None per query
  → itinerary generation continues with image_* fields left empty
  → PDF export simply omits the hero photo block for that day
```

---

## 16. Change Log

### v10.10 (July 2026) — Docker/Env Template Refresh + Supabase Production Runbook (infra housekeeping)

- **`.env.example` (backend)**: was badly stale — missing ~25 settings that `core/config.py` had grown to support (DB, JWT/auth, Google SSO, Resend email, OSM/retrieval feature flags, Reddit ingestion). Rewritten to cover every setting with free-tier guidance inline.
- **Fixed misleading `DATABASE_URL` default**: `core/config.py` defaulted to a non-functional placeholder Postgres string; now defaults to local SQLite (matches actual local dev usage in `.env`), zero setup required.
- **New `DATABASE_SSL_REQUIRE` setting**: Supabase (and most managed Postgres) require TLS that `asyncpg` won't negotiate automatically from a bare connection string — this was an undocumented footgun, now explicit and wired into `db.py`'s `connect_args`.
- **Fixed a real cross-environment migration bug**: `alembic upgrade head` against a *fresh* SQLite database crashed on migration `0001` (`events.event_metadata` used a hardcoded Postgres-only `JSONB` type with no SQLite fallback, while the ORM model already had one) — fixed by matching the ORM's `.with_variant(JSON(), "sqlite")`. Verified clean end-to-end on a brand-new SQLite file.
- **Fixed missing auto-migration on deploy**: `railway.toml`'s `startCommand` only ran `uvicorn`, meaning a fresh Supabase database would deploy with zero tables until someone manually ran migrations. Now `alembic upgrade head && uvicorn ...`.
- **`docker-compose.yml`**: added an optional `postgres` service (profile-gated, `docker compose --profile postgres up`) for local Postgres-parity testing without affecting the SQLite-by-default path.
- **New Supabase production setup runbook** in `docs/system-design.md` §8A: pooled-connection-string guidance (port 6543, avoids exhausting the free tier's 60-connection cap), the two required env vars, and the free-tier auto-pause-after-7-days caveat.
- Verified: 121 backend tests passing, no regressions; `alembic upgrade head` tested clean on a fresh SQLite file; `docker-compose.yml` validated as syntactically correct YAML.

### v10.9 (July 2026) — Foreign-Currency Budget Input

- **New `core/currency_convert.py`** — deterministic (regex, no LLM math) detection of a budget stated in one of 10 supported foreign currencies (USD, EUR, GBP, AED, SGD, AUD, CAD, JPY, THB, CHF), converted to INR via the free, keyless Frankfurter.app API with a 6-hour in-memory cache and hardcoded fallback rates.
- **Wizard chat**: now explicitly states INR is assumed the first time it asks for budget, and names the 10 supported alternative currencies. A detected foreign-currency amount is converted deterministically and both figures + the rate are stated transparently in Anya's reply; `config_patch.budget.amount` always stores the converted INR figure.
- Verified: 121 backend tests passing (no regressions), `tsc --noEmit` clean (no frontend changes needed), live curl-tested (`"$2000"` → `₹1,73,000`, first-ask message correctly mentions INR + currency options). See `TECHNICAL_DOCUMENTATION.md` §14 v10.9 and system-design.md §2.5 for full detail.

### v10.8 (July 2026) — Real Budget Estimator + Pre-Generation Feasibility Gate (backend + UI)

- **New `core/budget_estimator.py`** — deterministic (no LLM, free-tools-only) bare-minimum budget engine: destination cost tier + season + group composition + duration + traveller comfort level → flights/stay/food breakdown, total, and per-person figure. Returns `None` (forces a clarifying question) if group size is unknown.
- **Wizard chat UX change**: Anya no longer quotes a flat group-blind number from the parsing-only budget-tier table; she now asks for group size first, then states a real per-person + total estimate with what it covers/excludes (see §2.4).
- **New pre-generation feasibility gate in `LLMWizard.tsx`**: the LLM chat wizard now calls `/api/feasibility-check` before auto-generating (previously only the older structured form did). Infeasible budgets pause generation with a shortfall message + "Set budget to ₹X" / "Proceed anyway 🚀" / "Let me adjust something else" chips, rather than silently generating against an unrealistic number.
- **`feasibility_chain.py`**: the check now takes `max(llm_estimate, deterministic_floor)` and supports pre-booked flight/accommodation overrides (`prebooked_flights_inr`/`prebooked_accommodation_inr`) when a user states a real paid amount.
- **New comparison-mode row**: "Estimated Trip Budget (bare minimum)" in destination comparisons, using the same deterministic estimator per destination, cheapest destination highlighted as winner.
- Verified: 121 backend tests passing (no regressions), `tsc --noEmit` clean, live curl-verified end-to-end (ask-before-quote, per-person quote, infeasible-budget flag + floor + alternatives, comparison-mode budget row). See `TECHNICAL_DOCUMENTATION.md` §14 v10.8 for full detail.

### v10.6 (July 2026) — Admin Access Request/Approval Workflow

- **New `admin_requests` table** (migration `0003_admin_requests`) — tracks requester, status (`pending`/`approved`/`rejected`), optional message, reviewer, and timestamps.
- **New endpoints**: `POST /api/admin/requests` (any non-admin, idempotent while pending), `GET /api/admin/requests/me`, `GET /api/admin/requests` (admin-only list), `POST /api/admin/requests/{id}/approve` and `/reject` (admin-only, one-shot).
- **New emails**: every existing admin is notified the moment a request is created; the requester is notified of the approve/reject decision. Both best-effort via Resend with a dev-log fallback, same pattern as password reset.
- **New UI**: `/account` gained a "Request admin access" section (hidden for existing admins); `/admin` gained an "Admin access requests" panel above the metrics cards for reviewing pending requests.
- **Policy formalized**: `is_admin` was already impossible to set at signup (`SignupRequest` has no such field; DB defaults `false`) — this closes the gap by giving a formal, auditable, two-party path to grant it afterward. See §3C for the full data flow and §8A for the schema.
- Verified: 8 new integration tests (121 total backend tests passing); `tsc --noEmit` clean; 36 frontend tests passing; live end-to-end curl-tested against the running dev servers (signup → request → admin sees & approves → `is_admin: true` confirmed on `/auth/me` → admin-endpoint access confirmed).

### v10.5 (July 2026) — Admin Console Entry Point

- Added a conditional "Admin console" link (shield icon) to `UserMenu.tsx`'s dropdown, shown only when `user.is_admin === true`, positioned above "Log out" — previously `/admin` had no in-app entry point and had to be navigated to directly by URL.

### v10.4 (July 2026) — Local Testing Fixes: Auth Nav Indicator, Wizard Resume Race, Chip Backfill, SQLite FK Cascade

- **Auth nav indicator**: added `UserMenu.tsx` (Log in/Sign up when signed out; name/email + Log out dropdown when signed in), wired into `LandingHero`, `ThreeColumnLayout`, and `TopNav` — closes a gap where the app had no visible sign-in state or logout affordance outside `/account`.
- **Wizard resume race fix**: `LLMWizard.tsx`'s two mount effects (bootstrap + resume-after-auth) raced on the same mutable `pendingGeneration` sessionStorage flag, occasionally producing a duplicate/stale greeting after a signed-out user completed signup mid-wizard. Fixed via a single lazily-initialized snapshot shared by both effects plus a resume idempotency ref.
- **Chip-backfill safety net**: the primary Gemini-backed `wizard_chat()` path now deterministically backfills the 6 standard purpose chips if the LLM's first-turn response omits them, matching the guarantee the offline mock path already had.
- **SQLite FK cascade fix**: `apps/api/db.py` now sets `PRAGMA foreign_keys=ON` for SQLite connections only (local/dev), fixing silently no-op'd `ON DELETE CASCADE`/`SET NULL` behavior discovered during live local testing; zero effect on Postgres/prod. See `docs/scaling-tech-challenges.md` §7.
- Verified: 113 backend tests + 36 frontend tests pass; `tsc --noEmit` clean; all four fixes additionally live-tested against running local dev servers.

### v8.3 (July 2026) — Accounts, Auth Gate, Password Reset & Analytics

- Added authentication/session architecture covering email/password signup, Google OAuth SSO, cookie-based JWT + rotating refresh tokens, and password reset via Resend.
- Added data-flow documentation for auth, refresh rotation, pending-generation resume, and self-service account deletion.
- Documented the new Postgres schema (`users`, `refresh_tokens`, `events`, `password_reset_tokens`) and Supabase as the production Postgres host.
- Documented admin analytics endpoints plus the generic events table used for session/login/itinerary metrics and future Gemini/Pexels cost tracking.
- Updated itinerary-generation flow and environment-variable reference for the new auth/database stack.

### v10.2 (July 2026) — Brand Rename, Multi-City Reliability, Edit-in-Place, Dark Mode Everywhere

- **Rebrand**: WanderPlan → WanderPlanner across all UI strings, backend modules, docs, and assets (55 tracked files) — no functional change.
- **Multi-city wizard fix** (`chains/wizard_chat_chain.py`): added **Case D** — multiple explicitly-named places (e.g. "Colombo, Mirissa, and Yala") now correctly split into `destination` + `hops` instead of silently dropping all but the first city.
- **Country-mode resolution fix** (`chains/wizard_chat_chain.py`): naming a whole country now resolves to a concrete `destination`/`hops` the moment Anya proposes or the user confirms specific cities, instead of staying stuck in `destination_mode: "country"` with no real city — this was leaving budget/booking/travel-tips widgets blank downstream.
- **Frontend destination fallback** (`Column1Metrics.tsx`, `Column3Sidebar.tsx`): both now fall back to `destination_country` and gate widgets on "has a city OR a country" instead of requiring `destination.city` strictly, plus a "City +N" label for multi-hop trips.
- **PolaroidCard redesign**: replaced the oversized full-width 16:9 hero-video activity card with a compact horizontal thumbnail+text layout; added `onError` fallback to the gradient placeholder for 404'ing thumbnail URLs.
- **YouTube thumbnail reliability**: `useThumbnail` hook now only caches successful lookups (never caches misses) and retries up to 3x with backoff; `youtube-thumbnail` route pins `gl=US&hl=en` and pre-sends the EU consent cookie to reduce GDPR-interstitial scrape misses.
- **Theme multiselect regression fix**: backend now computes a `multi_select` boolean deterministically (`_is_multi_select_chips()`) and returns it explicitly in the `wizard-chat` response, replacing a fragile frontend keyword-matching heuristic that broke whenever Gemini varied chip wording.
- **Dark/light `ThemeToggle`** added to the itinerary page title bar and the Anya chat panel header — previously only present on the shared `/t/[slug]` page.
- **"Edit Trip" context fix**: reopening the wizard from an already-generated itinerary now seeds the existing trip config (with checkpoint already marked asked) instead of restarting the conversation from scratch; Stage-3 generate-signal phrases widened to recognize "regenerate"/"update it".

### v10.1 (July 2026) — Wizard Reliability + Visual PDF Export

- **Wizard truncation/JSON-leak fixes** (`chains/wizard_chat_chain.py`): `max_output_tokens` raised 800 → 2048; `_looks_like_valid_json()` now gates every Gemini response, triggering a retry (up to 3 attempts) on incomplete/truncated JSON instead of immediately falling back to salvage text; new `_strip_trailing_json_artifacts()` and `_strip_leaked_schema_tail()` helpers clean stray JSON punctuation and escaped schema-key echoes from any text ultimately shown to the user.
- **Wizard UX fixes** (`components/wizard/LLMWizard.tsx`): the "Generate my itinerary" CTA now derives from the backend's explicit Stage-3 signal (`summary !== null`) instead of a frontend required-field counter, so the text input stays available through Stage-2 optional follow-up questions (e.g. departure city); theme chip groups (Culture/Food/Adventure/etc.) are now multi-selectable via a toggle + "Continue" action instead of submitting on first click.
- **Itinerary PDF redesign** (`components/pdf/ItineraryDocument.tsx`): replaced the dense single-color layout with a colorful travel-journal style — one pastel card per day (7-color cycling palette), bold-label bullets, booking-link preview chips, and matching card treatment for Trip Essentials/Visa & Safety/Cost Breakdown/Packing Checklist. Removed emoji/arrow/≈ characters that rendered as broken glyphs under react-pdf's base Helvetica font.
- **Pexels photo enrichment** (new `services/pexels.py`): best-effort, non-blocking day-photo lookup added to `generate_itinerary()` — one landscape photo per day via `"{destination} {day theme}"` query, concurrent fetch, 6s timeout budget, in-memory query cache (500 entries), and required "Photo by X on Pexels" attribution rendered in the PDF. New optional `ItineraryDay` fields: `image_url`, `image_photographer`, `image_photographer_url`. New `PEXELS_API_KEY` env var (optional — app degrades gracefully without it).

### v10.0 (July 2026) — Security Hardening

Addresses 9 of the 10 findings in `docs/scaling-tech-challenges.md` §1 (full detail + status table: `docs/scaling-tech-challenges.md` §1a). Auth (#1) explicitly deferred.

- **SSRF fix** (`chains/extract_trip_chain.py`): DNS-resolve + reject private/loopback/link-local/reserved/multicast IPs (blocks cloud metadata IP `169.254.169.254`); manual redirect walk (max 3 hops, re-validated); 2MB response cap; content-type allowlist.
- **Rate limiting** (`core/rate_limit.py`, slowapi, IP-keyed, in-memory): `10/min` on all LLM-backed endpoints, `30/min` default elsewhere.
- **Share link hardening** (`routers/share.py`): `secrets.token_urlsafe(16)` (128-bit) replaces `uuid4().hex[:8]` (32-bit); both endpoints rate-limited.
- **Sanitized errors** (`core/errors.py`): all router exception handlers now log full detail server-side and return a generic message + reference id instead of `str(exc)`.
- **Prompt-injection guarding** (`core/prompt_guard.py`): `neutralize()` + `wrap_untrusted()` applied to RAG context, extract-trip fetched/pasted text, chat messages, and trip-config JSON across all LLM chains; frontend `lib/url-safety.ts` blocks unsafe `booking_url` schemes.
- **CORS hardening**: `allow_credentials=False`; `core/config.py` validator rejects `"*"` in `ALLOWED_ORIGINS`; CI wildcard check added.
- **Structured logging + redaction** (`core/logging_config.py`): JSON logs, PII redaction filter (emails/API keys/phone numbers); all `print()` calls replaced with `logger.*`.
- **Dependency hygiene**: `google-genai` pinned to `1.2.0`; `pip-audit` added to CI (advisory); `.github/dependabot.yml` added.
- **AGENTS.md review process**: `.github/CODEOWNERS` + CI job warns on AGENTS.md/CLAUDE.md changes.
- **Regression testing**: full backend pytest (89 passed/6 skipped), frontend `tsc --noEmit` + vitest (36 passed), live smoke tests of every modified endpoint in mock mode — no regressions.

### v9.0 (July 2026)
- RAG retrieval upgraded to hybrid search: BM25 (destination-scoped Qdrant scroll) fused with semantic cosine search via Reciprocal Rank Fusion, applied to every `semantic_search()` call
- HyDE query augmentation added (template-based hypothetical passage, `services/hyde.py`) for the "vibe" query variant
- Cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`) added, deliberately scoped to only the two true itinerary-generation call sites (`retrieve_context(..., enable_reranking=True)`); disabled by default elsewhere due to latency cost (~23.6 → ~7 req/s @ concurrency=50 when enabled globally)
- OSM POI ingestion built (`scrapers/osm.py`, Overpass API, weekly scheduled job) — `osm_pois` collection now live
- `itinerary_cache` collection now live — itineraries cached organically on successful generation, read back via cosine similarity ≥ 0.88
- 3-tier RAG-powered fallback chain implemented in `chains/itinerary_chain.py` for LLM failures: cache hit → OSM-grounded skeleton (`services/rag_fallback.py`) → RAG-tipped enhanced mock
- Fixed a concurrency bug where blocking `embed()`/Qdrant calls inside `async def` functions serialized on the event loop despite `asyncio.gather()`; now offloaded via `asyncio.to_thread()`, plus batched embedding of the 3 query variants in one call — throughput ~10 → ~23.6 req/s @ concurrency=50 (pre-hybrid/HyDE/rerank)
- Golden dataset + automated retrieval evaluation added (`apps/api/eval/golden_dataset.json`, `apps/api/eval/run_rag_eval.py`) — Precision@k/Recall@k/MRR/nDCG@k metrics
- Load testing tool added (`apps/api/load_test_rag.py`) to measure retrieval throughput/latency under concurrency

### v8.0 (June 2026)
- Wizard end-to-end fix: JSON history wrapping, retry logic, config_patch on ChatMessage, allFilled/isFieldFilled unification, smart mock fallback, prompt v5

### v7.0 (June 2026)
- Updated Anya wizard design to document prompt v4, persona-first approach, absolute speaking rules (§1a), and removal of `thought_process`
- Removed `thought_process` from `POST /api/wizard-chat` API contract; response is now `{ reply, chips, config_patch, ready_to_generate, summary }`
- Documented smarter extraction examples plus resilience fixes around bootstrap seeding, JSON fence parsing, stale closure protection, generate-loop handling, Gemini fallback behavior, and improved frontend error UX
