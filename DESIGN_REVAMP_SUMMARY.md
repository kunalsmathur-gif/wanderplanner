# WanderPlanner Design System — Implementation Summary

## Overview
This document describes WanderPlanner's current, adopted design system: a **Sky Blue + Adventure Orange** travel/tourism palette generated via the `ui-ux-pro-max` skill, paired with a **Space Grotesk + DM Sans** typography system. This supersedes an earlier "Passport Navy" travel-artifact direction (leather/map/stamp motifs), which was explored but never fully carried through the codebase and has now been retired.

---

## ✨ Current Design System

### 1. Color Palette — Sky Blue + Adventure Orange

Defined as semantic, dark-mode-aware CSS custom properties in `apps/web/app/globals.css` (`ui-ux-pro-max` skill output, Product Type: *Travel/Tourism Agency*):

| Token | Light | Dark | Usage |
|---|---|---|---|
| `--color-primary` | `#0EA5E9` (Sky 500) | `#38BDF8` (Sky 400) | Primary actions, links, focus ring |
| `--color-accent` | `#EA580C` (Orange 600) | `#FB923C` (Orange 400) | CTAs, highlights, the Listening Orb |
| `--color-background` | `#F0F9FF` (Sky 50) | `#040D14` (Ocean 950) | Page background |
| `--color-card` | `#FFFFFF` | `#071522` (Ocean 900) | Card/surface background |
| `--color-foreground` | `#0C4A6E` (Sky 900) | `#E0F2FE` (Sky 100) | Body text |
| `--color-border` | `#BAE6FD` (Sky 200) | `#0E3A57` (Ocean 700) | Borders/dividers |
| `--color-destructive` | `#DC2626` | `#F87171` | Errors, recording indicator |

All raw palette values live under `@theme inline` in `globals.css`; components should reference the **semantic** tokens (`var(--color-primary)`, etc.) rather than raw hex or raw palette scales, so they stay dark-mode aware.

### 2. Typography — Space Grotesk + DM Sans ("Tech Startup" pairing)

- **Display (`--font-display`):** Space Grotesk — headings (`h1`–`h6`), bold (700), tight tracking (`-0.03em`)
- **Body (`--font-body`):** DM Sans — body copy, tightened letter-spacing (`-0.01em`)
- **Mono (`--font-mono`):** JetBrains Mono — timestamps, numeric/data display

Loaded via `next/font/google` in `apps/web/app/layout.tsx`.

### 3. The Listening Orb — Signature Element

A custom SVG component (`apps/web/components/voice/ListeningOrb.tsx`) used in `ConversationalWizard` and `FloatingAnyaButton`:
- Breathing circle animation (idle vs. active pulse speed)
- Gradient fill from `var(--color-accent)` → `var(--color-primary)`
- Pulse rings in `var(--color-accent)` when actively listening
- Recording indicator dot in `var(--color-destructive)`

Now fully token-driven, so it adapts correctly between light and dark mode (previously hardcoded to the retired Passport Navy palette).

### 4. Shared UI Primitives

`globals.css` defines reusable, token-based classes used consistently across the app:
- `.btn` / `.btn-primary` / `.btn-accent` / `.btn-outline` / `.btn-ghost` — all enforce a 44px minimum touch target
- `.input`, `.card`, `.card-elevated`
- `.chip` / `.chip-selected` — used directly (e.g. in `ConversationalWizard`) instead of a separate dedicated chip component
- `.focus-ring` / `:focus-visible` — consistent keyboard focus treatment
- Global `prefers-reduced-motion` override

---

## 🧹 Cleanup From Previous Direction

The earlier "Passport Navy" travel-artifact concept (`#1A3A52` navy, `#E88D3A` amber, `#F7F4EF` ivory, Fraunces serif, dashed-border "stamp" chips) was only ever partially applied:

- `globals.css`, `layout.tsx`, and all live components use the Sky Blue + Orange / Space Grotesk system.
- `StampChip.tsx` was dead code — hardcoded to the retired navy/amber palette and not imported anywhere in the app. **Removed.**
- `ListeningOrb.tsx` still had hardcoded navy/amber hex values despite being actively used. **Migrated** to the current semantic tokens.

This document previously described the retired direction as if it were fully implemented; it has been rewritten to match what's actually in the codebase.

---

## 📐 Design Tokens Reference

```css
/* Semantic tokens (light values shown; see globals.css :root / .dark) */
--color-primary:    #0EA5E9;  /* Sky 500 — actions, links, focus */
--color-accent:     #EA580C; /* Orange 600 — CTAs, highlights */
--color-background: #F0F9FF; /* Sky 50 */
--color-foreground: #0C4A6E; /* Sky 900 */
--color-card:       #FFFFFF;
--color-border:     #BAE6FD; /* Sky 200 */
--color-destructive:#DC2626;

/* Typography */
--font-display: var(--font-space-grotesk); /* Space Grotesk */
--font-body:    var(--font-dm-sans);       /* DM Sans */
--font-mono:    var(--font-jetbrains);     /* JetBrains Mono */

/* Radius */
--radius-card: 12px;
--radius-lg:   16px;
```

---

## ✅ Status

**Status:** Sky Blue + Orange system is the single source of truth. All components should reference `var(--color-*)` semantic tokens — no new hardcoded hex values for brand colors.

**Implementation checklist**
- ✅ Landing, wizard, itinerary, chat, and shared-trip surfaces use the current token system
- ✅ Auth/legal/account surfaces (`/signup`, `/login`, `/forgot-password`, `/reset-password`, `/terms`, `/privacy`, `/account`) reuse the same design tokens and shared `.btn` / `.input` primitives
- 🟡 Admin dashboard surface is planned/in progress; when it lands, it must use the same tokens and primitives rather than introducing a separate admin design language

**Last Updated:** July 9, 2026 (added conditional Google SSO gating, actionable signup error messages, generation-stall watchdog, duplicate-key fix)

---

## 🧩 Component Updates (July 7, 2026)

### Auth, legal, account, and admin page surfaces
New full-page surfaces were added for authentication and compliance workflows:
- `/signup`
- `/login`
- `/forgot-password`
- `/reset-password`
- `/terms`
- `/privacy`
- `/account`
- `/admin` — **live and verified**, not a placeholder (superseded the earlier "planned/in progress" note below)

These pages intentionally **reuse the existing design system**:
- centered card shell and tokenized backgrounds
- existing `.btn`, `.btn-accent`, `.btn-outline`, and `.input` utility classes
- Space Grotesk + DM Sans typography pairing
- no new UI framework or parallel admin/auth design system introduced

Shared auth-specific components:
- `AuthLayout` — centered-card shell for auth pages
- `GoogleSignInButton` — branded CTA that still inherits the app token system
- `AuthHydrator` — non-visual bootstrap component that restores session state on app load and emits the `session_start` analytics beacon
- `UserMenu` ⭐ **NEW** — auth-status nav control (see below)

### Auth status indicator — `UserMenu.tsx` ⭐ NEW
Prior to this, the main app shell had **no visible sign-in state at all**: no "Log in"/"Sign up" CTA on the landing page, no indicator anywhere that you were already signed in, and no way to sign out short of navigating directly to `/account`'s danger zone. `UserMenu` is a single shared component wired into three chrome locations — `LandingHero`'s sticky nav, `ThreeColumnLayout`'s itinerary title bar, and `TopNav` — that reads `authStore` directly:
- **Signed out:** "Log in" text link + "Sign up" primary button, same visual weight as the existing "Plan a trip" CTA.
- **Signed in:** a bordered pill button showing `display_name`/`email`, click-to-open dropdown with a click-outside-to-close listener. Dropdown items: "Account settings", **"Admin console"** (only rendered when `user.is_admin === true`, with a shield icon, positioned directly above), and "Log out" (destructive red text, signs out then routes home).
- Skeleton-pulse placeholder while `authStore.status` is `loading`/`idle`, so the nav never flashes an incorrect state during the initial session-hydration fetch.
- Accepts an `inverted` prop for use on dark/photo chrome (`TopNav`) vs. the light card-style default.

### Admin console UI — `/admin` page ⭐ NEW
Full-page dashboard, gated client-side on `user.is_admin` (with the same 401→"please log in" / non-admin→"not allowed" split as the backend) and reachable from `UserMenu`'s "Admin console" link:
- **Stat cards** (4-up grid, responsive to 2-up on mobile): total users, sign-ups (30d), login success rate, itineraries generated (30d) — each using the existing `StatCard` primitive (icon + label + big number + optional sub-label), consistent with the rest of the app's card styling.
- **Cost & usage metrics** row: Gemini request count, Gemini token count, **estimated Gemini cost in ₹ (INR, not USD)** with `IndianRupee` icon and `en-IN` locale number formatting, Pexels free-tier call count.
- **Activity-over-time chart**: `recharts` line chart (sessions/signups/logins/itineraries) with a 7-day/30-day toggle.
- **Admin access requests panel** ⭐ NEW — sits above the stat cards so it's the first thing an admin sees on load. Lists pending requests (requester name/email + optional reason message) with green "Approve" / outlined-red "Reject" buttons; a pill badge shows the pending count next to the panel heading. Approving/rejecting immediately removes the row from the list (optimistic-feeling, backed by a real API round-trip) rather than requiring a manual refresh.
- **Danger zone**: bulk data-purge control, unchanged from the prior design (typed `DELETE ALL USERS` confirmation phrase).

### Admin access request UI on `/account` ⭐ NEW
A new "Admin access" section was added to the account-settings card, positioned between the identity block and the existing "Danger zone" — visible only to non-admin users (already-admin users don't need it, since they already have the console link in `UserMenu`):
- Default state: short explanation + a "Request admin access" outline button.
- After requesting: a "pending review" state with a clock icon, no way to re-request while pending (prevents spamming admins with duplicate emails — the backend is also idempotent here).
- If a prior request was declined: the explanation copy updates to acknowledge that and re-offers the request button.
- All state transitions are driven by `GET /api/admin/requests/me` on mount and the response of `POST /api/admin/requests`, no polling.

### Activity card redesign — `PolaroidCard.tsx`
The itinerary activity card was rebuilt from an oversized full-width 16:9 hero-video layout to a **compact horizontal layout**: a small 80–96px square thumbnail (Wikipedia photo or YouTube thumbnail) sits beside the activity text instead of above it. The previous layout pushed the actual itinerary copy (title, time, description) below a large video embed, making the center column feel unpolished and hard to scan. The card also gained an `onError` handler on the thumbnail `<img>` — if a YouTube thumbnail URL later 404s (deleted/restricted video), it now falls back to the existing deterministic gradient placeholder (`pickGradient(title)`) instead of showing a broken-image icon.

### Destination-aware widget gating — `Column1Metrics.tsx` / `Column3Sidebar.tsx`
Trip Metrics (budget, expense breakdown, currency widget) and the right-rail (travel tips, map, booking links) previously went completely blank whenever a trip was still in country-mode (e.g. "Italy" without a resolved city) or driven by the Anya wizard, which doesn't populate the legacy `collectedLabels` used by the older step-based wizard. Both components now accept `destination_country` as a fallback display value and gate widget rendering on "has *any* destination signal" instead of requiring a resolved city specifically. `Column1Metrics` additionally renders a "City +N" label when a trip has multiple hops.

### Dark/light mode reachability
`ThemeToggle` (sun/moon icon button) previously only appeared on the shared, read-only `/t/[slug]` trip page — there was no way to switch appearance from the main itinerary dashboard or from an open Anya chat panel, which are the two surfaces most users actually spend time in. The component now accepts a `className` override so its look can be adapted to different chrome (bordered icon button on light/card backgrounds, borderless white-on-color icon in the Anya chat header) and is wired into:
- `ThreeColumnLayout`'s title bar (next to `ShareButton`)
- `ChatPanel`'s header (next to the close button)

### Multi-select theme chips — reliability, not visuals
No visual change here, but worth noting for UX consistency: theme chip groups (Culture 🎨 / Food 🍜 / Adventure 🏔️ / etc.) toggle-select with a "Continue ✓" action, same as before. What changed is *how reliably* the UI knows a chip group is multi-select — it's now an explicit signal from the backend (`multi_select: true`) instead of a frontend guess based on chip label keywords, which could silently misfire whenever Gemini phrased the chip text differently.

---

## 🧩 Component Updates (July 9, 2026) — Local Testing Bug Fixes

### Conditional Google SSO button — `GoogleSsoSection.tsx` ⭐ NEW
`/signup` and `/login` previously always showed a "Continue with Google" button + "or" divider, even in environments where Google OAuth isn't configured (e.g. local dev with blank `GOOGLE_CLIENT_ID`/`SECRET`) — clicking it always failed with a confusing `{"detail":"Google sign-in is not configured."}` error. New `components/common/GoogleSsoSection.tsx` fetches `GET /api/auth/config` once on mount and only renders the button + divider when `google_sso_enabled` is true; fails closed (hidden) on load or on any fetch error. Both auth pages now use this component in place of the raw `GoogleSignInButton` + manual divider markup.

### Actionable signup error message
Signup with an already-registered email previously showed a deliberately generic `"Unable to sign up with these details."` (an account-enumeration mitigation). Per explicit product direction, this now reads `"An account with this email already exists. Try logging in instead."` — a clearer, more actionable message at a small cost to enumeration resistance. No frontend change was needed: both `/signup` and `/login` already surface the backend's `detail` string verbatim via `authErrorMessage()`.

### Generation-stall recovery — wizard chat
Previously, if the itinerary-generation SSE stream ever died in total silence (dropped connection, or in dev, a Fast Refresh page remount aborting the request mid-flight), the wizard's "generating" overlay stayed frozen on the initial "Starting up…" copy indefinitely — no error, no retry option, just a dead UI. `LLMWizard.tsx` now arms a 60-second watchdog (re-armed on every progress update) that, on total silence, surfaces `"Generation is taking much longer than expected and may have stalled. Please try again."` and returns the user to the chat so they can immediately retry.

### Duplicate-key render glitches in the wizard chat
Devtools previously showed a growing count of "Encountered two children with the same key" React warnings (up to 44 in one session) in the Anya chat message list, occasionally alongside visibly duplicated/misordered messages. Root cause: message ids were generated from a module-level counter that resets across a Next.js Fast Refresh reload in dev, while the component's message list (preserved across the reload) kept its old ids — new messages after any hot-reload collided with existing ones. Now uses `crypto.randomUUID()`, which can never collide regardless of reloads.

---

## 🧩 Component Updates (July 10, 2026) — Mobile Responsiveness Overhaul + Chat/Feasibility Bug Fixes

A large chunk of WanderPlanner's target audience tests/uses the product on mobile devices. This pass (via the `ui-ux-pro-max` skill) fixes real overflow/usability bugs found by manually testing at a 375px viewport, retires the old "desktop only" positioning, and fixes a batch of Anya wizard-chat bugs found in the same testing session.

### Removed `MobileWarningBanner` — mobile is now a first-class target, not tolerated
The banner telling mobile users "this experience is best viewed on desktop" directly contradicted the new goal of genuine mobile support, so it's been deleted entirely (`components/common/MobileWarningBanner.tsx`, plus its import/usage in `app/layout.tsx`). Added a defensive `overflow-x-hidden` on `<body>` to guard against any remaining horizontal-scroll regressions.

### Responsive header — `LandingHero.tsx` / `UserMenu.tsx`
The header previously overflowed a 375px viewport: full wordmark + tagline + a full-width "Plan a trip" button all forced onto one row, requiring horizontal scrolling to reach the login/signup controls. Now: icon-only logo and icon-only "Plan a trip" CTA below `sm:` (full wordmark/tagline/button text return at `sm:` and up), tighter padding/gaps, and a smaller hero heading on mobile. `UserMenu.tsx`'s "Log in" text link (redundant with "Sign up" for new visitors, and a common source of crowding) is now hidden below `sm:`, keeping only the compact "Sign up" button with `whitespace-nowrap`.

### Auth pages — footer link below the fold — `AuthLayout.tsx`
On a 375×667 viewport (iPhone SE, the smallest common target), the "Already have an account? Log in" footer link on `/signup` (and the equivalent on `/login`) was pushed below the fold, meaning existing users landing on signup by mistake might not notice they could just log in instead. Reduced mobile-only vertical spacing (card padding, section margins, title size) across `AuthLayout.tsx` (shared by signup/login/forgot-password/reset-password) so the footer link fits without scrolling — verified `scrollHeight === clientHeight` (667px = 667px) via Playwright.

### Frosted-glass wizard modal backdrop — `LLMWizard.tsx`
The Anya chat modal's backdrop was a flat, bland solid overlay (`bg-black/50` in dark mode, effectively fully white in light mode) — jarring and visually dead. Changed to a frosted-glass effect (`bg-white/30 backdrop-blur-md dark:bg-black/30`) so the blurred homepage remains subtly visible behind the chat in both light and dark mode. (Note: `ConversationalWizard.tsx` has the same old pattern but is confirmed dead/unused code, not rendered anywhere — left untouched.)

### Floating Anya button overlapping bottom mobile nav — `FloatingAnyaButton.tsx`
On the itinerary dashboard, the floating chat-launcher button sat at a fixed `bottom-6`, which overlapped the mobile bottom tab bar (Timeline/Map/Tips). Repositioned to `bottom-24` on mobile, keeping `lg:bottom-6` unchanged on desktop where there's no bottom nav to collide with.

> **Superseded in v10.58.0** — the orb no longer renders below `lg` at all, so there is nothing left to collide with and the `bottom-24` offset has been removed. See the v10.58.0 section at the end of this document.

### Full Map View "✕ Close" button unreachable — `ThreeColumnLayout.tsx`
The Full Map View toolbar packed the "Day view" label, a scrollable row of day-tabs, and the "✕ Close" button into a single row — with enough day-tabs (multi-day trips), Close could be pushed off-screen with no way to scroll back to it, trapping the user in full-screen map view. Restructured into two rows: label + Close always visible on the first row; day-tabs independently horizontally scrollable on the second.

### Map/day/venue selection made intuitive — `ItineraryTimeline.tsx`, `MapWrapper.tsx`, `ItineraryMap.tsx`, `appStore.ts`
Previously, viewing a specific activity's location on the map required manually switching to the Map tab and hunting for the matching pin — non-intuitive, especially on mobile where the map isn't visible alongside the timeline. `ActivityCard` is now clickable/keyboard-accessible: selecting an activity calls the existing `setHoveredItem()` (drives map highlight/fly-to) **and** a new `setMobileTab('map')` action (state lifted from a local `useState` into shared `appStore.ts` so both the timeline and the layout can drive/read it), jumping the mobile bottom-nav straight to the Map tab. Separately, the full-screen map was centering on a random Indian town ("Warud") instead of the actual destination for multi-city/country-mode trips, because `destination.lat/lon` is frequently `0/0` for these trips (never resolved at the top level) — `MapWrapper.tsx` now prefers the first itinerary item's real resolved coordinates for centering. Also added a `RecenterOnChange` effect component in `ItineraryMap.tsx`, since react-leaflet's `<MapContainer center>` prop only applies at initial mount — day switches previously left the map stuck on its first-rendered center.

### Anya wizard-chat bugs — budget, theme chips, pace chips, feasibility, generation hang
Found via live testing of the budget/theme/pace/feasibility conversation flow:
- **Luxury budget not recalculating**: asking for a "luxury stay" didn't raise the recommended budget — `core/budget_estimator.py`'s premium/economical keyword lists now substring-match (e.g. "luxur" catches "luxurious") instead of requiring an exact keyword.
- **Theme chips only single-select**: theme groups (Culture/Food/Adventure/etc.) are conceptually multi-select, but the UI only let one chip be picked — multi-select detection (both frontend and backend) now excludes generic "No preference"-style chips before evaluating, fixing false negatives.
- **Pace chips missing entirely**: asking about trip pace sometimes rendered zero chips (the LLM dropped them mid-turn) — the existing chip-backfill safety net previously only covered the very first "purpose" question; now applies to any turn where chips are missing and the wizard isn't ready yet.
- **Feasibility check too late, no explanation, confusingly worded fix**: the infeasible-budget warning only appeared right before generation (not as soon as pace/theme choices raised the estimate), gave no reason for the shortfall, and suggested an oddly-phrased absolute number instead of framing it as "increase your budget by ₹X." The deterministic bare-minimum floor is now traveller-tier-aware and the messaging is clearer.
- **Stuck at "Generate itinerary" with no CTA/progress indicator**: the LLM was hallucinating success/completion text without the `ready_to_generate` flag ever actually becoming true (the `purpose` field was never really captured) — added a regex guard (`_HALLUCINATED_GENERATION_RE`) and a `_next_missing_field_prompt()` helper to redirect the conversation back to the real next missing field instead of stalling silently.

### Progressively engaging generation loader
Previously the loading screen went completely silent for the 30–90s LLM call after only 2 status messages, giving no sense that anything was happening. `routers/itinerary.py` now runs generation as a background task while polling every 3s and streaming rotating filler status messages ("Planning day 1...", "Fetching local tips...", "Balancing your budget...", etc.) until the real result is ready.

---

## 🧩 Component Updates (July 29, 2026) — Voice-mic states + full E2E accessibility pass (v10.48.0)

Full findings + fix-by-fix detail: `docs/UI_UX_AUDIT_2026-07-29.md`. Backend/perf regression check: `TECHNICAL_DOCUMENTATION.md` §14 v10.48.0.

### Voice UX — reported live by a user, fixed as issues [#30](https://github.com/kunalsmathur-gif/wanderplanner/issues/30) / [#31](https://github.com/kunalsmathur-gif/wanderplanner/issues/31)
- **Persistent language toggle → one-time prompt.** `LLMWizard.tsx`'s header English/हिंदी toggle competed with the mic button for space on narrow viewports and could clip it off-screen entirely. Removed; a one-time "which language?" overlay now appears only the first time voice is activated in a session (`voiceLangAskedRef`).
- **Mic icon states, redesigned.** The mic button previously rendered a single hardcoded red/`MicOff`-style icon regardless of state — indistinguishable from "broken." Now four distinct states: grey idle `Mic`, `Volume2` while Anya is speaking, a visibly disabled state on unsupported browsers (Firefox), and an active/listening state with `animate-pulse`.
- **Active-state color: red → emerald, per explicit user pushback and the `ui-ux-pro-max` skill.** Red reads as "stopped/broken" (and this app already reserves `--_destructive` red for real errors); surveyed reference conventions (ChatGPT's green ring, Gemini's non-red pulse, Siri's non-red color wash) confirm red is not how top voice UIs signal "actively listening." Switched to `emerald-400`/`emerald-950`, chosen for guaranteed contrast in both themes without adding a new token.

### Full end-to-end accessibility/UX pass — every finding fixed, not a top-5 subset
A read-only `ui-ux-pro-max` audit covering landing, auth, wizard, dashboard, itinerary, account, admin, layout/nav, voice, and comparison surfaces surfaced ~25 findings; per explicit direction, all were fixed in the same pass rather than triaged to a subset:
- **Landing + wizard:** inspiration-card `<img>` → `next/image`; "Plan this" CTA no longer hover-only invisible on touch devices; extract-error banner now `role="alert"` with icon; a previously-dead `FEATURES` array now renders as a new "How it works" section; wizard modal gained a full focus trap + Escape-to-close + focus-return; both progress bars gained `role="progressbar"` ARIA; header icon buttons and chips bumped to the 44px tap-target minimum.
- **Auth flows:** `aria-invalid`/`aria-describedby` wired on all four auth pages' form fields; password-toggle and consent-checkbox tap targets enlarged; `returnTo` now survives the forgot-password → reset-password hop.
- **Dashboard + chat:** `BookingHub` tabs given visible labels and an always-focusable delete control; `BestTimeWidget` gained non-color-only best/avoid cues at larger text; `ChatPanel` is now responsive instead of a fixed-width overflow on mobile.
- **Itinerary view:** removed a nested-interactive pattern in `ItineraryTimeline`/`PolaroidCard` (single button control); `next/image` for timeline and sidebar thumbnails (`img.youtube.com` added to remote patterns); fixed an empty-origin "→ Destination" string in `BookingLinksSection`.
- **Account + admin:** labeled the type-to-confirm delete/purge inputs; admin usage chart gained a horizontal-scroll + text-legend + compact-table fallback for narrow viewports and non-visual access.
- **Layout + voice:** `UserMenu` gained full keyboard focus management (focus-first-item, Escape, arrow/Home/End nav, focus-restore) with new tests; `ListeningOrb`'s barely-visible red listening dot replaced with a clearly visible green status pill, animation made `prefers-reduced-motion`-safe.
- **Comparison components:** `DestinationSearchInput` gained full combobox/listbox ARIA + keyboard nav; `ComparisonPanel` reflows to a single column on mobile; `ComparisonGrid`'s label column is now sticky on scroll.

### Regression + performance verification
- **Backend untouched:** `git diff apps/api` empty across the entire pass; full pytest suite **917 passed / 6 skipped**; itinerary-timing instrumentation suite re-verified **22/22**.
- **Frontend:** `tsc --noEmit` clean; `vitest run` **126 passed** (10 files, incl. 2 new test files); real before/after `next build` bundle comparison: client JS **+0.6%** raw and gzip (+18KB / +5.6KB), fully attributable to the added a11y code, zero new npm dependencies.


## 🧩 Component Updates (July 30, 2026) — In-app feedback capture (issue #64)

New consumer-facing feedback surface, built entirely on existing design tokens — no new colors, fonts, or primitives introduced.

### Itinerary-level "missed the mark" flag — `ItineraryFeedbackFlag.tsx` ⭐ NEW
- One-shot per mount, no modal: idle text link → optional inline `<textarea>` for a reason → submit. Uses `--_border`/`--_card`/`--_primary`/`--_muted-fg` exactly as `AgentHandoffCard.tsx` does, for visual consistency with the existing sidebar cards.
- Wired into `Column3Sidebar.tsx` alongside `BookingLinksSection`/`AgentHandoffCard`, gated on an active day existing.

### Day/place-level thumbs-up/down — `ItineraryTimeline.tsx`
- Compact 👍/👎 buttons added to each `ActivityCard`'s metadata row (previously only shown when tags/video/booking links were present — the row is now always rendered since the reaction buttons are always there).
- Active state uses `--_success` (thumbs-up) and the existing `red-*`/`red-950` scale already used elsewhere for negative/destructive states (thumbs-down) — matches the emerald-for-positive / red-for-negative convention this doc's own v10.48.0 entry established for the voice mic states.
- Votes are changeable (click the other thumb to flip via `PATCH`), not one-shot — a deliberate UX choice for a low-friction reaction control, distinct from the itinerary-level flag's one-shot design.

### Regression + performance verification
- **Backend:** full pytest suite **1006 passed / 6 skipped**, 0 failed.
- **Frontend:** existing Playwright e2e suite (`apps/web/e2e/wizard.spec.ts`) **5/6 passed** — the one failure is a pre-existing, unrelated flake on the landing page (anonymous `/api/auth/me` 401 tripping a "no console errors" assertion), not touched by this change since the new components only render inside the itinerary view.

## 🧩 Component Updates (July 30, 2026) — Dashboard panel reorder, CTA prominence, itinerary-wide feedback redesign

Two back-to-back review passes on the itinerary dashboard's left/right panels, both live-tested on `localhost:3000` before commit.

### Round 1 — Left panel restructure
- **Compare Destinations hidden.** Removed the entry-point button from `Column1Metrics.tsx` only — `ComparisonPanel.tsx`, the `step3View` state machine, and `ThreeColumnLayout.tsx`'s conditional rendering are all left fully intact. Since nothing else calls `setStep3View('comparison')`, the feature is unreachable but trivially restorable (re-add the button) rather than deleted outright.
- **"Download PDF" → "Download Itinerary PDF"** (`PdfDownloadButton.tsx`, both button-text variants).
- **Trip Metrics condensed from 3 stacked rows to 1 row** — `Column1Metrics.tsx`'s `MetricRow` replaced with a `MetricCell` rendered 3-across (Destination / Budget / Days) inside a single bordered strip.
- **"Expense Breakup" → "Estimated Expenses"**, and the accordion now defaults to **collapsed** (`ExpenseBreakupCard.tsx`'s `useState(true)` → `useState(false)`) — expand-on-demand instead of always-open.
- **Local Expert Handoff → "Local Expert Help"**, moved from the right sidebar (`Column3Sidebar.tsx`) into the left panel (`Column1Metrics.tsx`), positioned after Estimated Expenses; CTA renamed **"Get It Booked" → "Get Quotation"** (`AgentHandoffCard.tsx`).
- **My Bookings moved below Local Expert Help** in the left panel (`BookingHub` reordered in `Column1Metrics.tsx`).

### Round 2 — CTA prominence + feedback overhaul (same day, follow-up review)
- **PDF download and Local Expert Help promoted to the page's two primary CTAs** — `PdfDownloadButton.tsx` restyled to `.btn-primary`, taller (`h-11`), with a brand-colored shadow; `AgentHandoffCard.tsx`'s section wrapper gained a 2px accent border, subtle gradient background, and shadow, with its CTA button enlarged to match.
- **Local Expert Help moved above Estimated Expenses** (reversing Round 1's ordering, per this round's explicit direction) in `Column1Metrics.tsx`.
- **My Bookings moved out of the left panel entirely, into the right sidebar** (`Column3Sidebar.tsx`), rendered below `BookingLinksSection.tsx`'s "🔗 Book This Trip" — unconditional (not gated on a resolved destination), matching its original always-visible behavior.
- **Per-item thumbs up/down replaced with a single itinerary-wide vote.** The previous design (👍/👎 on every `ActivityCard`, an unused `useItemFeedback` hook per card, plus a separate `ItineraryFeedbackFlag.tsx` "missed the mark" link in the sidebar) asked for a reaction far too often and, per direct user feedback, felt "completely broken." Replaced with:
  - `store/itineraryFeedbackStore.ts` — single source of truth for the vote/note/submission state (`idle → awaiting_note (on 👎) → loading → sent/error`), shared by both surfaces below so a vote given in one isn't re-asked in the other.
  - `store/feedbackPromptStore.ts` — tracks whether the dismissible popup has been shown/interacted-with this itinerary session (latches after first submit or dismiss, so it fires at most once per itinerary).
  - `ItineraryFeedbackWidget.tsx` — persistent inline "Was this itinerary helpful?" 👍/👎, rendered at the bottom of the centre itinerary section.
  - `TripFeedbackPopup.tsx` — dismissible popup, fixed bottom-right, rendered globally in `ThreeColumnLayout.tsx`. Triggered from four "leaving/acting on this plan" moments: **Edit Trip** (`Column1Metrics.tsx` — the closest real analog to "back," since no literal back button exists in this UI), **Generate/regenerate** (`LLMWizard.tsx::handleGenerate`, gated so a brand-new first generation with nothing to react to yet doesn't prompt), **Get Quotation** (`AgentHandoffCard.tsx::handleSubmit`), and **Share** (`ShareButton.tsx::handleShare`).
  - Thumbs-down on either surface asks an optional "What went wrong?" free-text note before submitting (`sentiment: "thumbs_down"`, `note`).
  - Both feedback stores reset automatically on every freshly generated itinerary (`itineraryStore.ts::setDays`), so a new plan gets its own clean feedback opportunity rather than inheriting the prior one's "already voted"/"already dismissed" state.
  - `ItineraryFeedbackFlag.tsx` deleted (fully superseded); `ItineraryTimeline.tsx` had its `useItemFeedback` hook and per-card 👍/👎 buttons removed entirely.
  - No backend changes — `POST/PATCH /api/itinerary-feedback` already supported `scope: "itinerary"` and `sentiment: "thumbs_up"|"thumbs_down"`; this was a pure frontend re-architecture. See `docs/system-design.md` §9C for the full before/after data-flow writeup.

### Regression + performance verification
- **Frontend:** `tsc --noEmit` clean across both rounds; `next build` clean (all 14 routes compiled) after each round.
- **Backend:** untouched — no `apps/api` changes in either round.
- Live-tested on `localhost:3000` (`next dev`) before commit, per explicit request.

## 🧩 Component Updates (July 31, 2026) — Mobile landing UX: inspiration above the fold, nav decluttered (v10.53.0)

Prompted by a live mobile screenshot review, evaluated with the `ui-ux-pro-max` skill. Full detail: `TECHNICAL_DOCUMENTATION.md` §14 v10.53.0.

### Inspiration surfaced sooner on mobile
- **Reordered `LandingHero.tsx`** so the Inspiration gallery renders immediately after the hero CTA, ahead of the Features/"How it works" strip — previously four stacked feature blocks pushed Inspiration below the fold on mobile.
- **Features condensed for mobile**: horizontally-scrollable chip row with smaller icons; descriptions moved to `sr-only` (still available to screen readers) and restored visually from `sm:` up, keeping the full descriptive grid on desktop.

### Nav decluttered
- **Removed the "Plan a trip" plane-icon button** from the sticky header — it duplicated the hero's "Start planning with Anya" CTA and added visual clutter as a second entry point for the same action.
- **Inspiration/FAQ anchor links made visible on mobile** (previously `hidden sm:block`, desktop-only) using the freed-up space, so mobile users can jump directly to either section instead of scrolling.

### Regression + performance verification
- **Frontend:** `tsc --noEmit` clean.
- **Backend:** untouched — no `apps/api` changes in this pass.

---

## 🧩 Component Updates (August 1, 2026) — Dashboard regrouped by intent; "Overview" renamed (v10.56.0)

Prompted by a live mobile review of the three-tab dashboard. Full detail:
`TECHNICAL_DOCUMENTATION.md` §14 v10.56.0 and `docs/system-design.md` §16 v10.56.

**The problem was naming and grouping, not styling.** The middle tab was called
"Overview" — a word that describes *where content sits* rather than *what it is
for* — and its contents had drifted: it held trip metrics, the whole-trip
actions, expenses **and** the expert handoff, while the actual booking links and
saved bookings sat two tabs away under the map. A user asking "what will this
cost and how do I book it" had to visit two tabs; a user asking "how many days
is this" had to leave the itinerary.

### The three sections, regrouped by what the user is doing

| Tab | Contents |
|---|---|
| **Itinerary** | Trip metrics, Edit Trip, Download PDF (new `TripSummaryHeader`) — then the day-by-day breakdown |
| **Booking & Expenses** (was "Overview") | Estimated expenses (collapsed), local expert help, book this trip, my bookings, currency |
| **Maps & Tips** | Map, best time to visit, travel tips & community |

- **`TripSummaryHeader.tsx` (new)** — trip metrics and the two whole-trip
  actions moved out of the left panel to sit directly above the timeline. They
  *describe the itinerary*, so they belong with it; on mobile they were the
  first thing users looked for and were parked behind a tab whose own content
  is consulted far less often.
- **`BookingExpensesPanel.tsx` (new, replaces `Column1Metrics`)** — ordered by
  the decision sequence: what will it cost → who can help me → where do I book
  → what have I already booked. Expenses stay **collapsed** by default; it is
  the tallest thing on the panel and most users only want the total.
- **`Column3Sidebar.tsx`** — booking sections moved out to the panel above,
  leaving it a coherent "where and when" section.
- **Desktop mirrors mobile deliberately** — the same three groupings in the
  same order across the three columns, so the two layouts stay one information
  architecture rather than two that drift apart.

### Expert card cut to a CTA + `AgentQuoteModal.tsx` (new)
The handoff card rendered an email field, a 100-word notes textarea and a word
counter inline. On a phone that pushed the actual CTA most of a screen down and
made a single "talk to an expert" offer read as a form to fill in. The card now
carries the pitch and one button; everything requiring typing happens in a
modal **after the user opts in** — a bottom sheet on phones (a centred box puts
the fields under the keyboard), centred from `sm` up.

Accessibility follows the v10.48.0 audit: labelled dialog, focus moved in on
open and restored on close, Escape to dismiss, Tab trapped inside, background
scroll locked. ⚠️ **Focus lands on the first form field, not the first
focusable** — the close button precedes the fields in DOM order, so the obvious
implementation lands the user on "dismiss", the one control they did not open
the dialog to press.

### Regression verification
- **Frontend:** `tsc --noEmit` clean; **24 new tests** covering the structural
  half of this change — `ThreeColumnLayoutTabs` (tab names, ordering, active
  state), `TripSummaryHeader` (metrics, destination fallback chain, the
  Edit-Trip feedback moment), `BookingExpensesPanel` (grouping, order, the
  no-destination branch) and `AgentQuoteModal` (the full focus contract).
- **Backend:** untouched — no `apps/api` changes in this pass.
- ⚠️ **Still needs a real device.** jsdom cannot see a tab label wrap at 320px,
  a keyboard cover a field, or a bottom sheet sit under a notch — those are
  MOB-006 to MOB-010 in `docs/eval-set.md` §7C.

---

## 🧩 Component Updates (August 2, 2026) — Auth card compacted; log-in promoted out of the footer (v10.57.0)

Prompted by a live look at `/signup`. Full detail:
`TECHNICAL_DOCUMENTATION.md` §14 v10.57.0 and `docs/system-design.md` §16 v10.57.

**Two complaints, and they pull against each other.** The card read heavy, and
the way *out* of it — "Already have an account? Log in" — sat below the card,
after every field, in muted grey. Making that link prominent costs vertical
space; the compaction has to pay for it.

### `AuthSwitch.tsx` (new) — both routes, at the top

A segmented **Sign up / Log in** control rendered inside the card above the
heading, via a new optional `switcher` slot on `AuthLayout`. Mirrored on
`/login` so the pair stays symmetric. `/forgot-password` and `/reset-password`
pass no switcher and are untouched.

- ⚠️ **Active state is carried by the pill, not by colour.** The obvious
  treatment — active `--_fg`, inactive `--_muted-fg` — leaves the inactive
  label at **~4.05:1** on the light-mode track (`#64748B` on `#F0F9FF`), and
  14px semibold is not WCAG large text, so it fails AA. Both labels therefore
  render at full `--_fg`; `--_card-elevated` + a `--_border` ring marks the
  current route. That also fixes dark mode, where a `--_card` pill on a `--_bg`
  track is nearly invisible — `#0D2236` on `#040D14` is not.
- Tabs are 44px (`min-h-11`), matching the touch-target standard the rest of
  the auth surfaces already use.
- ⚠️ **`returnTo` has to survive the tab hop.** The wizard and chat panel deep-
  link into `/signup?returnTo=…`; `/account` and `/admin` into
  `/login?returnTo=…`. Losing it returns the user to `/` after authenticating
  instead of to the gate they were stopped at — a silent wrong-page bug, not a
  visible failure. Tested at each entry point.

### Compaction — measured, not eyeballed

Card padding 32→20, form row gaps 16→12, label gaps 6→4, logo margin 32→24, and
the duplicated footer line removed.

| Measured at 696×825 | Before | After |
|---|---|---|
| Logo top → last element | 618px | **580px** (−6%) |
| Card | 500px | 513px |
| Log-in affordance | below card, muted `--_muted-fg` | tab 1 of 2, top of card |

The card *grew* 13px because it absorbed the 70px switcher — the surrounding
trim covers that and 38px besides. No page scroll at 696×825 or 375×812.

### Regression verification
- **Frontend:** `tsc --noEmit` clean; **15 new tests** — `AuthSwitch`
  (both routes present, `aria-current` on the live route only, `returnTo`
  encoded into both hrefs) and `AuthPages` (switcher renders ahead of the form,
  no duplicated footer link, and `returnTo` preserved across the switch for
  each of the four real deep-link origins). 168 passed total.
- **Backend:** untouched — no `apps/api` changes in this pass.
- ⚠️ **No screenshot and no real device.** The browser pane would not composite
  frames this session, so every number above is DOM geometry and computed
  style. Contrast ratios are arithmetic on token values, not measured pixels.

---

## 🧩 Component Updates (August 2, 2026) — Mobile tab bar frozen; Anya orb off the phone (v10.58.0)

Two live mobile complaints. Full detail: `TECHNICAL_DOCUMENTATION.md` §14
v10.58.0 and `docs/system-design.md` §16 v10.58.

### The tab bar is frozen — but the bug was the viewport, not the bar

The three section tabs only appeared once you scrolled to the very bottom.
Making them `fixed` is the fix that was asked for; it is not the whole fix.

- **`MobileTabBar` → `fixed inset-x-0 bottom-0 z-30 … lg:hidden`.** `z-30`
  sits under the Anya orb (`z-40`), feedback popup (`z-50`) and chat panel
  (`z-9998`), all of which are meant to cover the page.
- 🔴 **`h-screen` → `h-dvh` on `/itinerary` is the actual root cause.** On
  mobile `100vh` is the *large* viewport — it includes the strip behind the
  collapsing URL bar — so the column was taller than the visible screen and
  its last child began below the fold. Without this, `bottom-0` would have
  pinned the bar to the bottom of a viewport the user cannot see.
- ⚠️ **`pb-safe` was a no-op** — no such utility exists in `globals.css` or
  the theme, so notched phones drew the labels under the home indicator. Now
  a real `pb-[env(safe-area-inset-bottom)]` on the bar; the dead spacer div
  is gone.

### The Anya orb is desktop-only

~98px of permanent floating chrome over a phone-width column, and being
`fixed` it sat on top of whatever scrolled beneath it.

- **`FloatingAnyaButton`: `bottom-24 … lg:bottom-6` → `bottom-6 hidden lg:block`.**
  The `bottom-24` offset existed only to clear the mobile tab bar and is dead.
- ⚠️ **The orb is the only trigger for the persistent chat**, so hiding it
  outright would have removed `ChatPanel` from mobile entirely. New
  `AnyaTitleBarButton` (`lg:hidden`, `Sparkles`) sits in the already-frozen
  title bar next to Theme/Share/Account — same entry point, zero vertical cost.
- ⚠️ **"Edit Trip" is not the same entry point.** It reaches Anya, but through
  `openWizard()` — a full-screen config edit that blurs the dashboard and fires
  the `'back'` feedback prompt. The orb and title-bar button open the
  refine-in-place chat. Two surfaces; neither substitutes for the other.
- **Scroll reservation shrank** from `pb-36` (sized for the orb's ~194px band)
  to `pb-[calc(4.5rem+env(safe-area-inset-bottom))]` — the frozen bar alone.
  🔴 **If the orb ever returns to mobile this must grow again**, or it will
  cover the "Get Quotation" CTA and win the tap, exactly as before v10.56.1.

### Regression verification
- **Frontend:** `tsc --noEmit` clean, production build clean; **9 new tests** —
  frozen position, `z-30` layering, safe-area inset, scroll reservation, and
  the title-bar Anya button opening the chat store (`ThreeColumnLayoutTabs`),
  plus a new `FloatingAnyaButton` suite covering `hidden lg:block`, the dropped
  `bottom-24`, chat-not-wizard, and hide-while-open. **177 passed** total.
- **Backend:** untouched — no `apps/api` changes in this pass.
- ⚠️ **Needs a real phone, and a resized desktop window will not do.** jsdom
  cannot resolve `100dvh` against a collapsing URL bar and a desktop browser at
  375px has no collapsing URL bar to begin with — it passes whether or not the
  bug is there. `docs/eval-set.md` §7C MOB-012 to MOB-014.
