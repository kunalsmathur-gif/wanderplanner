# UI/UX Review — Voice Mode + Full App Accessibility Pass

**Date:** 2026-07-29 (shipped as v10.48.0)
**Scope:** Two voice-mode bugs reported live by a user (GitHub issues [#30](https://github.com/kunalsmathur-gif/wanderplanner/issues/30) and [#31](https://github.com/kunalsmathur-gif/wanderplanner/issues/31)), followed by a full read-only end-to-end review (`ui-ux-pro-max` skill) of landing, auth, wizard, dashboard, itinerary workspace, account, admin, layout/nav, voice, and destination-comparison surfaces. Unlike `UI_UX_AUDIT_2026-07-13.md` (audit-then-approve), the user asked for **every** finding fixed in the same pass, not a top-5 subset.
**Status:** All findings below are **fixed in v10.48.0**. No backend files were touched by any of this work (`git diff apps/api` is empty) — see "Regression check" at the bottom.

---

## 1. User-reported (filed as issues, fixed first)

### 1.1 Language toggle — clunky, clips the mic icon on mobile (#30)

`LLMWizard.tsx` rendered a persistent English/हिंदी header toggle at all times. On narrow viewports it competed with the mic button for the same row and pushed the mic off-screen.

**Fix:** removed the persistent toggle entirely. A one-time overlay ("Which language would you like to speak?") now appears the *first* time the user activates the mic in a session (`voiceLangAskedRef` gates it to once), then gets out of the way — no permanent chrome, nothing to clip on mobile.

### 1.2 Mic icon — red-with-slash at all times, no distinct states (#31)

Both mic buttons (wizard header pill + footer bar) used a single hardcoded red/`MicOff`-style icon regardless of whether voice was idle, listening, or unsupported — indistinguishable from "broken."

**Fix:** four explicit states, each with its own icon + color:
- **Idle** — grey `Mic` icon, no animation.
- **Listening/active** — emerald `Mic` icon with `animate-pulse` (see §1.3 on why emerald, not red).
- **Speaking (TTS)** — `Volume2` icon.
- **Unsupported** (e.g. Firefox) — visibly disabled state instead of a silently dead button.

### 1.3 Follow-up: is red the right "active" color?

User pushback: red reads as "stopped/broken," not "in use" — asked to reconsider using the `ui-ux-pro-max` skill rather than guessing.

Ran the skill's palette lookup against this app's own tokens (`apps/web/app/globals.css`): `--_destructive` (red) is reserved app-wide for real errors, and a `--_success` (emerald) token already exists for positive/active states with no on-color conflict. Changed the "listening" state from red to **emerald** (`emerald-400`/`emerald-950` for guaranteed contrast in both themes) — matches the convention used by ChatGPT (green ring), Gemini (blue pulse — deliberately not red), and Siri (color wash, never red) surveyed as reference points: red is reserved for permission-denied/error states, not the actively-listening state.

---

## 2. Full end-to-end review findings (by area), all fixed

### Landing + wizard
- Inspiration cards used raw `<img>` (no responsive sizing/lazy-load/modern formats) → converted to `next/image`; added `images.remotePatterns` for `upload.wikimedia.org`.
- "Plan this" CTA on inspiration cards was `opacity-0` (hover-only) — invisible affordance on touch devices with no hover → now `opacity-70` by default, `100` on hover/focus.
- Extract-from-URL error rendered as plain text, no icon, no assistive-tech signal → `role="alert"`, destructive-token color, warning icon.
- A `FEATURES` array had been defined in code but never rendered anywhere (dead content) → built into a new "How it works" trust section between the hero and the inspiration gallery.
- Wizard modal had no focus trap, no Escape-to-close, and lost focus-return to the triggering element → added full trap (`dialogRef`/`previouslyFocusedRef`), `handleDialogKeyDown` (Escape + Tab cycling), and focus restored to the opener on close.
- Both progress bars in the wizard had no ARIA semantics → added `role="progressbar"` + `aria-valuenow/min/max` + label.
- Header icon buttons were 36px (below the 44px minimum touch target) → bumped to 44px; chip buttons got larger padding.

### Auth flows (login / signup / forgot-password / reset-password)
- Form fields lacked `aria-invalid`/`aria-describedby` wiring to their error text — a screen-reader user got no association between a field and why it failed → added throughout all four pages.
- Password-visibility toggle and the signup consent checkbox were both under the 44px tap-target minimum → enlarged.
- `returnTo` (where to send the user after auth) was silently dropped across the forgot-password → reset-password hop → now threaded through via `useSearchParams` + `sessionStorage` so a user who started a password reset from a deep link lands back there, not the homepage.

### Dashboard + chat
- `BookingHub.tsx` category tabs (Flights/Stays/Activities) were icon-only with no accessible name → visible labels added; the delete-booking control was hover-only (unreachable on touch/keyboard) → always visible and focusable.
- `BestTimeWidget.tsx` used "🎯 Peak"/"💤 Off-season" color-only cues at small text size → bumped text size, added non-color cues (icon + label) so the distinction doesn't rely on color perception alone.
- `ChatPanel.tsx` was a fixed-width floating panel that ran off small viewports → responsive width, `inset-x-4 bottom-4` on mobile, `w-[360px] right-6 bottom-24` from `sm:` up.

### Itinerary view
- `ItineraryTimeline.tsx` / `PolaroidCard.tsx` nested an inner clickable region inside an outer clickable card (nested-interactive, invalid and confusing for assistive tech) → collapsed to a single `button` control per card.
- Thumbnails used raw `<img>` → `next/image`; `Column3Sidebar.tsx` thumbnails likewise. Added `img.youtube.com` to `next.config.ts` remote patterns.
- `BookingLinksSection.tsx` rendered a broken "→ Destination" string when the origin city was unresolved (empty origin) → fixed the string construction.

### Account + admin
- Delete-account and admin bulk-purge confirmation inputs (type-to-confirm patterns) had no associated `<label>` → added.
- Admin's usage chart had no fallback for narrow viewports or for a user who can't read the chart at all → added horizontal scroll, a text legend, and a compact data-table fallback.

### Layout + voice
- `UserMenu.tsx` (the account dropdown) had no focus management: opening it didn't focus the first item, Escape didn't close it, arrow keys/Home/End didn't navigate, and closing it didn't return focus to the trigger → all added, with new tests (`__tests__/components/UserMenu.test.tsx`).
- `ListeningOrb.tsx` had a tiny, low-contrast red dot as its only "listening" indicator, and its animation ran unconditionally regardless of `prefers-reduced-motion` → rebuilt as a clearly visible green "Listening" status pill, animation now reduced-motion-safe. New test file `ListeningOrb.test.tsx`.

### Destination comparison
- `DestinationSearchInput.tsx` had an unlabeled input and no combobox semantics (no `role="combobox"`/`listbox`, no arrow-key navigation) → full ARIA + keyboard nav added.
- `ComparisonPanel.tsx` was a fixed multi-column grid that didn't reflow on mobile → `grid-cols-1 sm:grid-cols-2`.
- `ComparisonGrid.tsx`'s first (label) column scrolled out of view alongside the data columns on a wide comparison → made sticky.

---

## 3. Regression + performance check (see also `TECHNICAL_DOCUMENTATION.md` §14 v10.48.0)

- **Backend:** `git diff apps/api` is empty — zero backend files touched by any fix above. Full pytest suite run clean: **917 passed, 6 skipped, 0 failed**. `tests/unit/test_itinerary_timing.py` (the LLM-latency instrumentation from v10.47.0) re-verified in isolation: **22/22 passed**.
- **Frontend build/type/test:** `tsc --noEmit` clean across `apps/web`; full `vitest run` — **126 passed** across 10 files (incl. the 2 new test files above), 0 failures.
- **Frontend bundle-size, real before/after `next build`** (fixes stashed vs. applied, same Next.js/Turbopack version, same 14 routes generated both times): client JS raw **2,944,818 B → 2,962,893 B (+18,075 B, +0.6%)**; gzip **937,680 B → 943,306 B (+5,626 B, +0.6%)**. No new npm dependencies (`package.json`/`package-lock.json` diff is empty) — the entire delta is the added a11y logic (focus trap, combobox keyboard handling, extra legend/label markup), proportional to the functionality gained, not bloat.
- **Real-world perf note (not visible in the bundle diff):** the `next/image` conversions (`LandingHero`, `PolaroidCard`, `Column3Sidebar`) should *reduce* actual transferred image bytes and improve LCP at runtime via automatic resizing/modern-format encoding/lazy-loading — a genuine optimisation, just not one a static JS bundle comparison can show.

## 4. Not done / deliberately out of scope

- Real LLM-load/cost benchmarking (`apps/api/load_test_rag.py`) was **not** run — it requires live Gemini/embedding API keys not present in this environment and would incur real cost; skipped because zero backend code changed, so there is nothing for it to have regressed.
- ~~Two pre-existing repo-hygiene issues surfaced incidentally while setting up backend tests, **not fixed here** (out of scope): the committed `apps/api/.venv` uses Python 3.9 while the code requires ≥3.11 (`datetime.UTC`); `requirements.txt` pins `httpx==0.28.1` while `requirements-dev.txt` pins `httpx==0.27.0`.~~ — ✅ **Fixed 2026-07-29.** `requirements-dev.txt`'s `httpx` pin now matches `requirements.txt` (`0.28.1`). `main.py` gained a `sys.version_info < (3, 11)` guard at the very top of the file — before any other import — so a stale local `.venv` now fails fast with an actionable message instead of a cryptic `ImportError: cannot import name 'UTC' from 'datetime'` several frames deep in `core/scheduler.py`. README's backend setup step now calls out the 3.11+ requirement explicitly and warns that a bare `python3 -m venv .venv` can silently pick up an older system Python (this is exactly how the local `.venv` ended up on 3.9). Full backend suite re-verified on a freshly-built 3.12 venv: 883 passed / 6 skipped.
