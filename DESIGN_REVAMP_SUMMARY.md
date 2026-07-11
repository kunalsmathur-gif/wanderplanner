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
