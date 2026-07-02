# WanderPlan Design System — Implementation Summary

## Overview
This document describes WanderPlan's current, adopted design system: a **Sky Blue + Adventure Orange** travel/tourism palette generated via the `ui-ux-pro-max` skill, paired with a **Space Grotesk + DM Sans** typography system. This supersedes an earlier "Passport Navy" travel-artifact direction (leather/map/stamp motifs), which was explored but never fully carried through the codebase and has now been retired.

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

**Last Updated:** July 1, 2026
