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

**Last Updated:** July 7, 2026

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
- `/admin` *(planned/in progress; backend metrics exist, frontend page not yet verified as shipped)*

These pages intentionally **reuse the existing design system**:
- centered card shell and tokenized backgrounds
- existing `.btn`, `.btn-accent`, `.btn-outline`, and `.input` utility classes
- Space Grotesk + DM Sans typography pairing
- no new UI framework or parallel admin/auth design system introduced

Shared auth-specific components:
- `AuthLayout` — centered-card shell for auth pages
- `GoogleSignInButton` — branded CTA that still inherits the app token system
- `AuthHydrator` — non-visual bootstrap component that restores session state on app load and emits the `session_start` analytics beacon

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
