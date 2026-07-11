# Next-Session TODO — GTM Phase 1 Execution

**Last updated:** 2026-07-11 (end of session)
**Context:** Executing the Phase 1 roadmap in [GTM_STRATEGY.md](GTM_STRATEGY.md). Items 1–2 shipped this session (v10.15 + v10.16, see `TECHNICAL_DOCUMENTATION.md` §14). This file is the pick-up point for the next session.

---

## ✅ Done this session (for context)

1. **Itinerary-corpus few-shot retrieval** (v10.15) — `services/search.py::retrieve_itinerary_examples()` wired into both LLM generation paths. 13 tests.
2. **Hidden-gem scoring + crowd dial** (v10.16) — `services/gems.py`, `TripConfig.crowd_preference`, prompt + retrieval-bias wiring, Anya extraction (live-verified: "less crowded hidden gems" → `offbeat`), 💎 timeline badge. 15 tests.
3. Strategy docs: `GTM_STRATEGY.md` created; `STARTUP_EVALUATION.md` addendum (score 5→6/10).

Backend unit suite: **148 passed**. `tsc --noEmit` clean.

---

## ⏭️ Remaining Phase 1 items (in execution order)

### 1. Refinement hard-constraints + visible diff UI (the "Harry Potter test") — NEXT UP

The #2 user-interview gap: refinements are prompt nudges, not commitments. Plan:

1. **Interest → entity expansion chain**: named interest ("Harry Potter fan", "F1 enthusiast") → candidate POIs via one small Gemini call (pattern: `chains/extract_trip_chain.py`).
2. **Verification step**: geocode/confirm each candidate against `osm_pois` / Wikivoyage before use — reuse the OSM-verification approach from `services/gems.py`. Unverified candidates are dropped, never pinned.
3. **Hard pinning**: survivors become must-include constraints in the generation/refinement prompt (a `PINNED_POIS` section with lat/lon), not suffix text.
4. **Visible diff after each refinement**: compute added/removed/swapped items between old and new itinerary (match by title similarity) and render chips in the Anya chat panel ("Added: WB Studio Tour (Day 3)"). Touch points: `chains/chat_refine_chain.py` (check actual filename), `ChatRefineResponse` in `apps/web/types/index.ts`, the persistent Anya chat component.
5. Keep the scale/latency/cost rules: one small extraction LLM call max per refinement, verification via existing collections (no new APIs), diff computed client-side or in the response path (cheap).

### 2. Refinement-fidelity eval suite (vs ChatGPT)

- ~20 named-interest prompts scored on whether the right verified POIs appear in output; build on `docs/eval-set.csv` / `apps/api/eval/`.
- This is the **Phase 1 kill-criterion gate** (see GTM_STRATEGY §5): if we can't measurably beat ChatGPT here, pivot to pure B2B tooling.
- Output doubles as marketing content ("WanderPlanner vs ChatGPT on 50 refinement tests").

### 3. Affiliate tracking on existing deep-links

- **Blocked on founder action**: register for Viator, GetYourGuide, Skyscanner affiliate programs, then supply the IDs.
- Code side is small: append affiliate params to the existing booking deep-links (grep `booking_url` construction + `KAYAK`/`Viator` link builders).

---

## 🔧 Operational / hygiene items

- **Run corpus ingestion once locally** (`chains/itinerary_corpus_extraction_chain.py::ingest_itinerary_corpus()`, needs `GEMINI_API_KEY`) so v10.15's retrieval actually has data — until then generation uses the clean "No reference itineraries available" fallback. Same for gem intel: it needs `reddit` + `osm_pois` data for the destination (both have existing ingestion jobs).
- **E2E check of gems in a real generation**: sign in on local, generate a Phuket/Goa trip with crowd dial = Hidden Gems, confirm 💎-tagged items with provenance appear. (Unit-tested but not yet observed end-to-end with live data.)
- **`WizardForm.tsx` is dead code** (never imported; `LLMWizard` is the live wizard). The crowd-dial UI added to `PaceBudgetSection.tsx` is unreachable until that form is revived — decide whether to delete the form wizard or mount it somewhere.
- Consider a `HIDDEN_GEM` metric in admin analytics (how often gems get generated/kept) once real traffic exists.

## 💰 Deferred by cost decision (revisit later)

- **BestTime.app live crowd-forecast layer** (paid API) — corpus signal shipped first; live layer is a premium/B2B upsell candidate.
- **Booking.com affiliate pricing for accommodation** — blocked on partner-account approval (see TECHNICAL_DOCUMENTATION §14 backlog table).

## 📋 Phase 2 preview (don't start until Phase 1 eval gate passes)

Agent mode (branded PDF export, markup field, client-shareable link) · live budget grounding (Amadeus free tier, IRCTC fare tables) · hand-onboard 10 agents. Full detail + kill/go criteria in [GTM_STRATEGY.md](GTM_STRATEGY.md) §5.
