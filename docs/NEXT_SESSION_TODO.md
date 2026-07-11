# Next-Session TODO — GTM Phase 1 Execution

**Last updated:** 2026-07-12 (end of session)
**Context:** Executing the Phase 1 roadmap in [GTM_STRATEGY.md](GTM_STRATEGY.md). Items 1–3 shipped (v10.15–v10.17, see `TECHNICAL_DOCUMENTATION.md` §14). This file is the pick-up point for the next session.

---

## ✅ Done last session (for context)

1. **Refinement hard-constraints + visible diff UI** (v10.17, the "Harry Potter test") — GTM Phase 1 item 3:
   - `chains/interest_expansion_chain.py` (named interest → ≤10 candidate places, one `gemini-2.5-flash` call) + `services/poi_pinning.py` (verify vs `osm_pois` fuzzy-match with real coords, `wiki` text fallback; unverified = dropped, never pinned) + `TripConfig.pinned_pois` (cap 8) + `PINNED MUST-INCLUDE PLACES — HARD CONSTRAINTS` prompt block in both LLM paths.
   - `chat_refine` orchestration: detects `named_interest`, pins survivors into `config_patch`, honest reply about dropped candidates; LLM-authored `pinned_pois` stripped (integrity guard).
   - Frontend: in-place regeneration from the Anya panel (old plan survives failures), `lib/itineraryDiff.ts` added/removed/moved chips, 📌 pin chips + timeline badge.
   - 29 new tests (177 total green), tsc clean. **Live-verified** detection→expansion→honest-degradation against the running Gemini API (9 real Harry Potter places expanded for London; all dropped against empty local Qdrant with the honest reply).
   - ⚠️ Found live: `gemini-2.5-flash` burns `max_output_tokens` on hidden thinking → tight caps truncate JSON. Expansion cap is 2048 until google-genai ≥2.x lands (then `ThinkingConfig(thinking_budget=0)`). `extract_trip_chain.py`'s 512 cap has the same latent risk.

---

## ⏭️ Remaining Phase 1 items (in execution order)

### 1. Refinement-fidelity eval suite (vs ChatGPT) — NEXT UP

- ~20 named-interest prompts scored on whether the right **verified** POIs appear in output; build on `docs/eval-set.csv` / `apps/api/eval/`.
- v10.17 gives the scoring hook for free: check output items for the `pinned` tag / pinned titles, and diff fidelity across refinements.
- This is the **Phase 1 kill-criterion gate** (GTM_STRATEGY §5): if we can't measurably beat ChatGPT here, pivot to pure B2B tooling.
- Output doubles as marketing content ("WanderPlanner vs ChatGPT on 50 refinement tests").

### 2. Affiliate tracking on existing deep-links

- **Blocked on founder action**: register for Viator, GetYourGuide, Skyscanner affiliate programs, then supply the IDs.
- Code side is small: append affiliate params to the existing booking deep-links (grep `booking_url` construction + `KAYAK`/`Viator` link builders).

---

## 🔧 Operational / hygiene items

- **E2E of the pinned-POI positive path with real data**: needs `osm_pois` ingested for a destination + a signed-in session. Flow: sign in on local → generate a London trip → Anya: "I'm a huge Harry Potter fan" → confirm 📌 pins with real coords, in-place regeneration, and diff chips. (Negative/degradation path live-verified 2026-07-12; positive path is unit-proven only.)
- **Run corpus ingestion once locally** (`chains/itinerary_corpus_extraction_chain.py::ingest_itinerary_corpus()`, needs `GEMINI_API_KEY`) so v10.15's retrieval has data. Same for gem intel (`reddit` + `osm_pois`) and pin verification (`osm_pois`/`wiki`) — all three features currently degrade cleanly to their no-data fallbacks on a fresh `:memory:` Qdrant.
- **E2E check of gems in a real generation**: sign in on local, generate a Phuket/Goa trip with crowd dial = Hidden Gems, confirm 💎-tagged items with provenance appear.
- **`WizardForm.tsx` is dead code** (never imported; `LLMWizard` is the live wizard). The crowd-dial UI in `PaceBudgetSection.tsx` is unreachable until that form is revived — decide whether to delete the form wizard or mount it somewhere.
- **`chat_refine` has no retry on transient Gemini 503s** (hit one live this session; the generation chain retries but refine doesn't) — consider one cheap retry with backoff.
- **Dependabot: google-genai → 2.10.0** is open; when merged, add `ThinkingConfig(thinking_budget=0)` to `interest_expansion_chain.py` (drop cap to ~512) and consider the same for `extract_trip_chain.py`.
- Consider a `HIDDEN_GEM` / `PINNED` metric in admin analytics (how often gems/pins get generated & kept) once real traffic exists.

## 💰 Deferred by cost decision (revisit later)

- **BestTime.app live crowd-forecast layer** (paid API) — corpus signal shipped first; live layer is a premium/B2B upsell candidate.
- **Booking.com affiliate pricing for accommodation** — blocked on partner-account approval (see TECHNICAL_DOCUMENTATION §14 backlog table).

## 📋 Phase 2 preview (don't start until Phase 1 eval gate passes)

Agent mode (branded PDF export, markup field, client-shareable link) · live budget grounding (Amadeus free tier, IRCTC fare tables) · hand-onboard 10 agents. Full detail + kill/go criteria in [GTM_STRATEGY.md](GTM_STRATEGY.md) §5.
