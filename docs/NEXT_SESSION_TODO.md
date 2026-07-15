# Next-Session TODO — GTM Phase 1 wrap-up → Phase 2

**Last updated:** 2026-07-15 (mid-session update — Qdrant Cloud + GEMINI_MODEL hygiene fixes shipped)
**Context:** The UI/UX audit's §2 (high-priority polish) is now **fully fixed** — v10.21.0 (dark-mode token pass + error copy + dead WizardForm deleted) and v10.22.0 (on-demand PDF, one `en-IN` currency/date formatter app-wide, BestTime "Busiest/Quietest" labels). Remaining Phase 1 surface: audit §3 (share-page SSR+OG, metadata, a11y leftovers) + the founder-blocked affiliate item. **Infra update this session: local dev + Railway prod are now both on a shared, persistent Qdrant Cloud cluster (was `:memory:` everywhere) — this unblocks the RAG-refresh/E2E-with-real-data items below.** Eval results remain published in [docs/eval-results/](eval-results/README.md); founder still needs to post externally.

---

## ✅ Done last session (for context)

1. **v10.21.0 — audit §2.1+§2.2:** deleted dead `WizardForm.tsx` + `wizard/sections/*` (8 files, ~1,000 lines, pre-rebrand palette); moved ItineraryOverview / ExpenseBreakupCard / FeasibilityCard / BookingLinksSection / PdfDownloadButton / ErrorState onto `--_*` tokens (semantic colors via `dark:` variants); error copy de-jargonised ("backend is running" gone); BookingHub tab `aria-label`s in passing.
2. **v10.22.0 — audit §2.3–§2.5:** `PdfDownloadButton` rewritten to on-demand `pdf().toBlob()` with `@react-pdf/renderer` dynamic-imported at click (was: full PDF render on every dashboard mount); NEW `lib/format.ts` — `formatCurrency` (en-IN, `₹1,50,000` everywhere incl. Trip Metrics + LLMWizard resume line) and `formatDayDate` ("Sat, 14 Nov" in day tabs, share page, overview); CurrencyWidget copy softened + tokenized; BestTimeWidget "🎯 Peak"→"👥 Busiest (crowds & prices)", "💤 Off-season"→"💤 Quietest" + tokenized.
3. 44 web tests pass (36 + 8 new `format.test.ts`) · `tsc --noEmit` clean · backend untouched (223 backend tests unaffected).
4. **Qdrant Cloud migration (⭐ NEW, 2026-07-15):** both local dev (`apps/api/.env`) and Railway prod now point at a shared, persistent Qdrant Cloud cluster (free 1GB tier) instead of `:memory:` — verified via `core/qdrant.py::get_qdrant()` creating all 5 collections (`wiki`, `reddit`, `osm_pois`, `itinerary_cache`, `itinerary_corpus`) live on the cluster from both the local process and Railway's redeployed instance. Railway health check (`/health`) confirmed green post-redeploy. Local Colima/Docker Qdrant container (used only as a stepping stone) has been torn down — no longer needed for this. Documented as a full production runbook in `docs/system-design.md` §9, plus the corresponding storage-scale math for *why* eager global destination coverage would still break even a Cloud cluster in `docs/scaling-tech-challenges.md` §8.
5. **GEMINI_MODEL hygiene fix:** switched from `gemini-2.5-flash-lite` (repeatedly 503-congested) to `gemini-2.5-flash` in both `apps/api/.env.example` and Railway's `api` service env vars — matches what live evals were already using process-level.

## ⏭️ Remaining items (in suggested order)

### 1. UI/UX audit follow-ups — §3 ([UI_UX_AUDIT_2026-07-13.md](UI_UX_AUDIT_2026-07-13.md)) — ✅ DONE this session

- **§3.2 share-page SSR + OG tags** — done. `app/t/[slug]/page.tsx` is now an async Server Component (`params` awaited as `Promise<{slug}>`, per Next 16); fetches the share payload server-side via new `lib/sharedTrip.ts::getSharedTrip()` for both `generateMetadata` and the render. OG/Twitter tags carry destination + duration; a dynamic `opengraph-image.tsx` (`next/og` `ImageResponse`, 1200×630 gradient card) renders per-trip so unfurls in WhatsApp/Slack are no longer blank. 📌/💎/📸 tag badges now render in the shared view (same style as `ItineraryTimeline`). Verified end-to-end against a live local backend: correct `<title>`/OG meta, 200 PNG from the OG image route, badge markup present, and the "expired or doesn't exist" fallback still works for unknown slugs.
- **§3.1/§3.3** — done. Added `layout.tsx` (Server Component, since the pages themselves are `'use client'`) exporting per-route `metadata` for `/login`, `/signup`, `/account` (also `noindex` on `/account`, it's private); `/t/[slug]` gets metadata via `generateMetadata` above (also `noindex` — shared links aren't meant to rank). Audited all `<button>`s app-wide for icon-only instances missing `aria-label`; found and fixed the two adult/kids counter +/− stepper buttons in `ConversationalWizard.tsx`'s `CounterCard` (previously nothing announced what was being incremented/decremented). Everything else icon-only already had labels; confirmed audit's note that CurrencyWidget's refresh button no longer exists and `/dev` cards are correctly out of scope.
- 44 web tests pass · `tsc --noEmit` clean · production build (`next build`) succeeds, `/t/[slug]` and its `opengraph-image` route both correctly marked dynamic (`ƒ`, server-rendered on demand).

### 2. Eval recall chase — done (v10.23.0, 2026-07-15)

Tuned the anti-distractor rule in `chains/interest_expansion_chain.py`'s `_EXPANSION_SYSTEM_PROMPT` to allow famous theatres/walk-of-fame monuments/celebrity residences as "specific" — this was silently dropping true positives (Hollywood Walk of Fame, Prithvi Theatre). Validated with direct probes + spot-checks + full backend suite (255 passed, 2 pre-existing unrelated failures) before spending on a live rerun. Live rerun (after founder raised the Gemini spend cap): **fidelity 0.983 (was 0.975), recall 0.958 (was 0.938)**, inclusion/stability still 1.000, honesty still 4/4. RF-009/RF-012 fixed; RF-001/RF-015 traded as the "still missing one" case between runs — confirmed via re-probe to be `temperature=0.1` sampling variance, not a residual rule defect. Published numbers updated everywhere they're tracked: `docs/eval-results/README.md` (+ new dated reports), `docs/GTM_STRATEGY.md` §5, `docs/eval-set.md` §4V, `docs/system-design.md`/`TECHNICAL_DOCUMENTATION.md` changelogs, and the pitch deck (which had drifted to a stale pre-v10.20 number). Founder still needs to post externally.

### 3. Affiliate tracking — blocked on founder

Register Viator / GetYourGuide / Skyscanner affiliate programs and supply IDs. Link formats fixed since v10.20.0, so the code side is a small param-append in `BookingLinksSection.tsx` + `cityCodes.ts` coverage check.

## 🔧 Operational / hygiene items (carried over)

- **Run the RAG refresh jobs now that Qdrant Cloud is live (unblocked ⭐):** `ingest_reddit()` (6-hourly cadence), `ingest_osm_pois(dest)` looped over `KNOWN_DESTINATIONS` (weekly cadence — ~134 destinations × (Overpass query + 2s politeness delay), expect a long sequential run), and `ingest_itinerary_corpus()` (monthly cadence — needs `GEMINI_API_KEY`, costs Gemini calls for extraction+embedding). Qdrant is no longer the blocker — this can be run directly from the backend venv whenever convenient. This also unblocks the carried-over corpus-ingestion and E2E-with-real-data items below.
- **Implement demand-driven ingestion** (design sketched 2026-07-15, see `docs/scaling-tech-challenges.md` §8): new Postgres `destination_ingestion_state` table + `ensure_destination_ingested()` gatekeeper in the itinerary-generation path + rewrite `core/scheduler.py::_refresh_osm_pois` to refresh only previously-requested destinations instead of looping the static `KNOWN_DESTINATIONS` list. Do this **before** any push to expand destination coverage beyond the current curated 134 — see §8 for the math on why eager global pre-ingestion breaks storage/Overpass rate limits/cost regardless of vector DB choice.
- **Wire up `ingest_wikivoyage()`** (`scrapers/wikivoyage.py`) — discovered this session to be fully implemented and idempotent but **not called from any scheduled job or request path** (system-design.md previously and incorrectly documented it as "on-demand, triggered at itinerary generation time"; now corrected). Small, independent fix — wire it into the same on-demand gatekeeper as the item above, or a lightweight scheduled job in the interim.
- **E2E pinned-POI positive path with real data** (needs `osm_pois` ingested + signed-in session): London trip → "I'm a huge Harry Potter fan" → 📌 pins, in-place regen, diff chips. Also the themes-backstop path ("add some zen gardens to my trip").
- **Corpus ingestion once locally** (`ingest_itinerary_corpus()`, needs `GEMINI_API_KEY`) for v10.15 retrieval/gem intel/pin verification with real data.
- **E2E gems check** (crowd dial = Hidden Gems → 💎 with provenance).
- **Dependabot google-genai → 2.10.0** (PR #8, still open/unmerged as of this update): when merged, add `ThinkingConfig(thinking_budget=0)` to `interest_expansion_chain.py` (cap back to ~512); consider same for `extract_trip_chain.py`.
- `HIDDEN_GEM`/`PINNED` admin metrics once real traffic exists · optional §4U: point `run_rag_eval.py` at `retrieve_context()` (non-trivial — `retrieve_context()` takes a full `TripConfig`, not the golden dataset's simple query+destination shape; needs a schema refactor, not a quick swap).
- Windows gotcha: `git commit -m` with embedded double quotes breaks in PowerShell 5.1 — write message to a file, use `git commit -F`.

## 💰 Deferred by cost decision (revisit later)

- **BestTime.app live crowd-forecast layer** (paid API) — premium/B2B upsell candidate.
- **Booking.com affiliate accommodation pricing** — blocked on partner approval.

## 📋 Phase 2 preview (publish is done — Phase 2 can start once founder signs off on the piece)

Agent mode (branded PDF export, markup field, client-shareable link) · live budget grounding (Amadeus free tier, IRCTC fare tables) · hand-onboard 10 agents. Full detail + kill/go criteria in [GTM_STRATEGY.md](GTM_STRATEGY.md) §5.
