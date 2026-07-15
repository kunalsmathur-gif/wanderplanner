# Next-Session TODO — GTM Phase 1 wrap-up → Phase 2

**Last updated:** 2026-07-15 (end of session, v10.22.0)
**Context:** The UI/UX audit's §2 (high-priority polish) is now **fully fixed** — v10.21.0 (dark-mode token pass + error copy + dead WizardForm deleted) and v10.22.0 (on-demand PDF, one `en-IN` currency/date formatter app-wide, BestTime "Busiest/Quietest" labels). Remaining Phase 1 surface: audit §3 (share-page SSR+OG, metadata, a11y leftovers) + the founder-blocked affiliate item. Eval results remain published in [docs/eval-results/](eval-results/README.md); founder still needs to post externally.

---

## ✅ Done last session (for context)

1. **v10.21.0 — audit §2.1+§2.2:** deleted dead `WizardForm.tsx` + `wizard/sections/*` (8 files, ~1,000 lines, pre-rebrand palette); moved ItineraryOverview / ExpenseBreakupCard / FeasibilityCard / BookingLinksSection / PdfDownloadButton / ErrorState onto `--_*` tokens (semantic colors via `dark:` variants); error copy de-jargonised ("backend is running" gone); BookingHub tab `aria-label`s in passing.
2. **v10.22.0 — audit §2.3–§2.5:** `PdfDownloadButton` rewritten to on-demand `pdf().toBlob()` with `@react-pdf/renderer` dynamic-imported at click (was: full PDF render on every dashboard mount); NEW `lib/format.ts` — `formatCurrency` (en-IN, `₹1,50,000` everywhere incl. Trip Metrics + LLMWizard resume line) and `formatDayDate` ("Sat, 14 Nov" in day tabs, share page, overview); CurrencyWidget copy softened + tokenized; BestTimeWidget "🎯 Peak"→"👥 Busiest (crowds & prices)", "💤 Off-season"→"💤 Quietest" + tokenized.
3. 44 web tests pass (36 + 8 new `format.test.ts`) · `tsc --noEmit` clean · backend untouched (223 backend tests unaffected).

## ⏭️ Remaining items (in suggested order)

### 1. UI/UX audit follow-ups — §3 only ([UI_UX_AUDIT_2026-07-13.md](UI_UX_AUDIT_2026-07-13.md))

- **§3.2 share-page SSR + OG tags** (own milestone — the viral surface unfurls blank in WhatsApp/Slack; 📌/💎 badges also missing there). Share data is public → server-render `t/[slug]` with OG title/description (+ OG image if cheap), and render pinned/gem badges in the shared view.
- **§3.1/§3.3**: per-page `<title>`/metadata for `/login` `/signup` `/account` `/t/[slug]`; aria-labels for remaining icon-only buttons (note: audit's "CurrencyWidget refresh button" no longer exists — widget has no refresh control; `/dev` cards are dev-only/low priority).

### 2. Optional eval recall chase (only if publishing follow-ups need it)

RF-001/RF-009/RF-012 all miss on the same mode: interest expansion not proposing one truth-set place. The anti-distractor rule may be too conservative for celebrity-home/theatre venues (Mannat, Prithvi Theatre). Decide: tune expansion or accept + already-disclosed. Any change = rerun live (~$0.40) before touching the published numbers.

### 3. Affiliate tracking — blocked on founder

Register Viator / GetYourGuide / Skyscanner affiliate programs and supply IDs. Link formats fixed since v10.20.0, so the code side is a small param-append in `BookingLinksSection.tsx` + `cityCodes.ts` coverage check.

## 🔧 Operational / hygiene items (carried over)

- **Force RAG data refresh (one-off, requested 2026-07-15 — bypass the weekly/monthly cadence):** run the three scheduler jobs from `core/scheduler.py` directly instead of waiting for their `IntervalTrigger`s: `ingest_reddit()` (6-hourly cadence), `ingest_osm_pois(dest)` looped over `KNOWN_DESTINATIONS` (weekly cadence — ~135 destinations × (Overpass query + 2s politeness delay), expect a long sequential run), and `ingest_itinerary_corpus()` (monthly cadence — needs `GEMINI_API_KEY`, costs Gemini calls for extraction+embedding). **Blocked when attempted: Qdrant was not running on `localhost:6333`** (all three jobs upsert into it) — start Qdrant first, then run a one-off script with the backend venv. `GEMINI_API_KEY` is confirmed set in `apps/api/.env`. This also unblocks the carried-over corpus-ingestion and E2E-with-real-data items below.
- **GEMINI_MODEL:** local `.env` still `gemini-2.5-flash-lite` (503-congested repeatedly); live evals use process-level `gemini-2.5-flash`. Consider switching the default.
- **E2E pinned-POI positive path with real data** (needs `osm_pois` ingested + signed-in session): London trip → "I'm a huge Harry Potter fan" → 📌 pins, in-place regen, diff chips. Also the themes-backstop path ("add some zen gardens to my trip").
- **Corpus ingestion once locally** (`ingest_itinerary_corpus()`, needs `GEMINI_API_KEY`) for v10.15 retrieval/gem intel/pin verification with real data.
- **E2E gems check** (crowd dial = Hidden Gems → 💎 with provenance).
- **Dependabot google-genai → 2.10.0**: when merged, add `ThinkingConfig(thinking_budget=0)` to `interest_expansion_chain.py` (cap back to ~512); consider same for `extract_trip_chain.py`.
- `HIDDEN_GEM`/`PINNED` admin metrics once real traffic exists · optional §4U: point `run_rag_eval.py` at `retrieve_context()`.
- Windows gotcha: `git commit -m` with embedded double quotes breaks in PowerShell 5.1 — write message to a file, use `git commit -F`.

## 💰 Deferred by cost decision (revisit later)

- **BestTime.app live crowd-forecast layer** (paid API) — premium/B2B upsell candidate.
- **Booking.com affiliate accommodation pricing** — blocked on partner approval.

## 📋 Phase 2 preview (publish is done — Phase 2 can start once founder signs off on the piece)

Agent mode (branded PDF export, markup field, client-shareable link) · live budget grounding (Amadeus free tier, IRCTC fare tables) · hand-onboard 10 agents. Full detail + kill/go criteria in [GTM_STRATEGY.md](GTM_STRATEGY.md) §5.
