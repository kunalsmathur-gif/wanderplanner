# UI/UX + Copy Audit — Production-Readiness Review

**Date:** 2026-07-13 (v10.19.0)
**Scope:** Landing, auth pages, conversational wizard, itinerary workspace (desktop + mobile + dark mode), chat panel, share page, account page, and the API surfaces they render. Reviewed against the running app (dev servers, mock Tokyo itinerary via `/dev`) plus source.
**Status:** §1.1 + §1.2 (trust-critical) and §3.4 **fixed in v10.20.0 (2026-07-14)** — honest tip provenance enforced in code, flight deep-links rebuilt on working formats (`lib/cityCodes.ts` static IATA map + honest fallback copy), rickroll mock id removed. §2.1 + §2.2 **fixed in v10.21.0 (2026-07-15)** — all six flagged components moved onto the `--_*` token system (semantic colors via `dark:` variants), error copy de-jargonised, dead `WizardForm.tsx` + sections deleted; BookingHub tab `aria-label`s (part of §3.3) done in passing. All other items remain findings only. Tracking summary lives in [NEXT_SESSION_TODO.md](NEXT_SESSION_TODO.md) §2; this doc is the full record.

---

## 1. Trust-critical (fix before any public push)

These two directly contradict the product's core wedge — "verified truth, no fabricated provenance" ([GTM_STRATEGY.md](GTM_STRATEGY.md) §2) — on production surfaces.

### 1.1 Travel tips fabricate community provenance

`apps/api/routers/travel_tips.py`, rendered in the dashboard's "Travel Tips & Community" section.

- The Gemini prompt (`_TIPS_PROMPT`) instructs the model to generate tips that *"read like they come from real travelers on Reddit, travel blogs, and travel forums"* and to label each with `source: r/travel | r/solotravel | TripAdvisor | Travel Blog | Lonely Planet | Nomadic Matt` — i.e. **LLM-invented content presented as sourced community content**, with `post_url` pointing at generic search pages.
- `_fallback_tips()` hardcodes six template tips with **fake upvote counts** (`score: 127, 94, 156, 203`) and the same real-brand source labels. The UI renders these as `r/travel ↑ 127`.
- The genuinely real path (`_fetch_reddit_tips` — live Reddit search with real permalinks and scores) is fine and worth keeping.

**Why it matters:** the published comparison piece will argue that competitors' suggestions are "unverifiable" — while our own sidebar displays invented tips wearing Reddit/TripAdvisor branding and invented scores. A single screenshot of this defeats the whole positioning.

**Direction (when fixes are approved):** keep real Reddit tips as-is; relabel LLM/template tips honestly (e.g. source `"General tip"`, no score, no third-party brand names), or drop the fabricated-source styling entirely.

### 1.2 Booking deep-links are (very likely) broken

`apps/web/components/itinerary/BookingLinksSection.tsx:42–52`, promised in-UI as "Links open pre-filled with your trip details."

- **Google Flights** uses the long-retired fragment syntax `https://www.google.com/flights?hl=en#search;f=…;t=…` — Google ignores it and opens the bare Flights homepage.
- **Skyscanner** path format expects lowercase IATA/entity codes (`/transport/flights/del/nrt/260114/`) but receives URL-encoded city names.
- **MakeMyTrip** `itinerary=` expects city codes (`DEL-BOM-14/01/2026`) but receives raw city names.

**Why it matters:** the pre-fill promise is broken today, and GTM Phase 1 item 5 (affiliate tracking) plans to append affiliate params to these exact links — auditing/fixing the URL formats must come first or the affiliate clicks land on dead pre-fills.

---

## 2. High — visible polish and correctness

### 2.1 Dark-mode gaps (hardcoded light-only styling)

The design system (`globals.css` `--_*` tokens + `.dark` overrides) is solid, but these components bypass it:

| File | Issue |
|---|---|
| `components/itinerary/ItineraryOverview.tsx:66` | `bg-white border-slate-200`, no `dark:` variants |
| `components/dashboard/ExpenseBreakupCard.tsx:39` | `bg-white border-slate-200` |
| `components/wizard/FeasibilityCard.tsx:124` | `bg-white border-slate-200` |
| `components/itinerary/BookingLinksSection.tsx:162` | `bg-white … hover:bg-blue-50` |
| `components/pdf/PdfDownloadButton.tsx` | `bg-slate-100 text-slate-700` both states |
| `components/common/ErrorState.tsx` | Light-only **and** uses the pre-rebrand palette (`#1E40AF`, `#0F172A`) instead of `--_primary`/`--_fg` |

Note: the old wizard sections (`components/wizard/sections/*`, reached only via dead `WizardForm.tsx`) carry the same `#1E40AF` palette — deleting the dead code (already a TODO item) shrinks this fix surface.

*(False alarm, verified OK: timeline `PolaroidCard`s appeared stuck-white in dark mode during automated review — that was a browser-automation rendering artifact; the component's `var(--_card)` theming is correct.)*

### 2.2 Developer-speak in user-facing error copy

- `ErrorState.tsx:19` — "Check that the **backend** is running and retry."
- `ConversationalWizard.tsx:1270` — "please make sure the **backend** is running and try again."

Users don't run backends. Replace with plain language ("Something went wrong on our side — please try again in a moment."). Other error copy (rate-limit, connection, stall watchdog in `LLMWizard.tsx`) reads fine.

### 2.3 PDF generated eagerly on every dashboard mount

`PdfDownloadButton.tsx` wraps `@react-pdf`'s `PDFDownloadLink`, which renders the full document to a blob **on mount** — CPU cost on every dashboard load whether or not the user downloads (observed as a pre-created `blob:` URL on page load). Switch to on-demand generation (`pdf().toBlob()` on click).

### 2.4 Date & currency formatting inconsistencies

- **Raw ISO dates in UI:** day tabs show `2026-11-14` (`ItineraryTimeline.tsx:190`); share page same (`t/[slug]/page.tsx:85`). Should be human-formatted ("Fri, 14 Nov").
- **Currency:** Trip Metrics shows `INR 150,000` (`Column1Metrics.tsx:63`, `toLocaleString()` with browser locale) while the landing page uses `₹1,80,000` (Indian digit grouping). Pick one formatter (e.g. `Intl.NumberFormat('en-IN', {style:'currency', currency})`) app-wide.
- **CurrencyWidget** renders raw "Currency rates unavailable." in the sidebar when the rates call fails — degrade silently or soften ("Rates temporarily unavailable").

### 2.5 Best-Time widget copy ambiguity

`BestTimeWidget.tsx` output reads: "Best months to visit: Jul, Aug, Dec" then "🎯 Peak: Jul, Aug" then "💤 Off-season: Jun, Sep". "Peak" overlapping "best" is confusing — peak season usually connotes *crowds/prices to avoid*, and the crowd-dial feature elsewhere treats it that way. Clarify labels (e.g. "Busiest", "Quietest") or reconcile with the crowd-preference language.

---

## 3. Medium — metadata, a11y, growth surfaces

### 3.1 Per-page metadata missing

`/login`, `/signup`, `/account`, `/t/[slug]` all render the landing `<title>` ("Wanderplanner — Free AI Travel Planner…"). Add per-route `metadata` exports (client pages need a layout or generateMetadata wrapper).

### 3.2 Share page is a blank unfurl

`app/t/[slug]/page.tsx` fetches client-side, so shared links have **no OG tags** — they unfurl blank/generic in WhatsApp/Slack/iMessage, exactly where shared trips spread. Consider server-rendering the share page (it's public data) with OG title/description and an OG image. Also: the share view renders items as plain 📍 rows — **📌 pinned and 💎 hidden-gem badges don't appear**, so the differentiating features are invisible on the most viral surface.

### 3.3 Unnamed icon-only controls (a11y)

- Currency refresh button in the metrics column (`CurrencyWidget`) — no `aria-label`.
- BookingHub category tab buttons (Flights/Stays/Activities) — icon+text visually but unnamed in the accessibility tree (`ref` audit showed 3 anonymous buttons).
- `/dev` page cards (dev-only, low priority).

Keyboard support elsewhere is good (ActivityCard has `role="button"` + Enter/Space handling; mobile tab bar uses `aria-current`).

### 3.4 Mock data rickroll

`app/dev/mockData.ts` uses YouTube id `dQw4w9WgXcQ` for Senso-ji. Dev-only today, but the mock itinerary path can serve production users via the Tier-3 fallback chain — worth confirming the fallback path never carries this id (backend `_mock_itinerary` uses empty `youtube_video_id`, so exposure is dev-page only; still, cheap to swap).

---

## 4. Copy notes (minor, wording-level)

- Landing FAQ "190+ countries — … and thousands more" — "thousands more" grammatically attaches to countries; say "thousands of cities and destinations."
- Signup checkbox: "I agree to the Terms of Service and Privacy Policy." — links exist; good. Consider matching the CTA case style used elsewhere ("Create account" vs landing's "Start planning").
- Anya's refine-chat empty state, wizard chips, honesty replies ("better honest than invented!"), account-page danger zone, and shared-trip expired-link copy are all **strong — no changes suggested**.

## 5. Verified OK (no action needed)

- **Mobile layout** (375px): bottom tab bar (Itinerary / Overview / Map & Tips) present and functional, no horizontal overflow, tap-to-map behavior from activity cards is thoughtful.
- **Landing page**: hero copy, inspiration cards (accessible names on every card button), FAQ, footer CTA.
- **Wizard**: conversational flow, step chips, quick-reply chips, voice affordances, graceful paste-URL fallback ("Could not extract trip details. Opening the wizard instead…").
- **Account page**: proper type-DELETE confirmation, privacy-policy disclosure, admin-request flow copy.
- **Share page**: expired-link error state and CTA footer.
- **Theming architecture**: token system + `.dark` overrides are clean; gaps are per-component (see 2.1), not systemic.

## Suggested fix order (when approved)

1. §1.1 + §1.2 (trust-critical; small diffs, high stakes)
2. §2.1 + §2.2 as one "dark mode + error copy" polish pass
3. §2.3–§2.5 formatting/performance pass
4. §3.2 share-page SSR + OG (own milestone — touches routing and backend share endpoint)
5. §3.1/§3.3 metadata + a11y sweep
