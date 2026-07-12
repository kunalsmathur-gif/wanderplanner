# Next-Session TODO — GTM Phase 1 Execution

**Last updated:** 2026-07-12 (end of session, v10.18)
**Context:** Executing the Phase 1 roadmap in [GTM_STRATEGY.md](GTM_STRATEGY.md). Items 1–4 shipped (v10.15–v10.18, see `TECHNICAL_DOCUMENTATION.md` §14). This file is the pick-up point for the next session.

---

## ✅ Done last session (for context)

1. **Refinement-fidelity eval suite** (v10.18) — GTM Phase 1 item 4, the kill-criterion gate:
   - `eval/refinement_fidelity_dataset.json` — 20 cases (16 positive incl. 6 Indian destinations, 4 negative honesty cases), 76-POI OSM + 5-chunk wiki fixture truth-set with per-destination distractors; every positive case carries one invented candidate that must drop.
   - `eval/refinement_scoring.py` — pin recall / precision / exactly-once inclusion / re-refinement stability / composite fidelity / honesty; reuses `poi_pinning`'s production name matcher. `eval/run_refinement_eval.py` — offline replay (deterministic, free, in-memory Qdrant, regression gate at fidelity 1.000) / `--live` (real Gemini, ~$0.02/case) / `--baseline` (ChatGPT comparison table → `eval/out/refinement_fidelity_report.md`).
   - `eval/baselines/chatgpt_refinement.template.json` — recording protocol + paste-ready prompts for the ChatGPT baseline.
   - 23 new tests (`tests/unit/test_refinement_eval.py`, incl. dataset consistency through the REAL `verify_candidates_sync`); **200 passed / 6 skipped**. Offline run verified end-to-end: 20/20, fidelity 1.000, honesty 100% (the deterministic ceiling).

---

## ⏭️ Remaining Phase 1 items (in execution order)

### 1. Produce & publish the kill-criterion numbers — NEXT UP (mostly founder actions)

- **Founder:** run `python -m eval.run_refinement_eval --live` from `apps/api` (venv python, needs `GEMINI_API_KEY`; fixtures are self-contained — no ingestion needed). ~$0.40 total.
- **Founder:** record the ChatGPT baseline per `eval/baselines/chatgpt_refinement.template.json` (fresh session per case, first answer only, ~30 min), save as `chatgpt_refinement.json`.
- Rerun with `--baseline`, review `eval/out/refinement_fidelity_report.md`, decide **kill/go** (GTM §5): can we measurably beat ChatGPT on verified-place fidelity? Publish the report as marketing content if yes.
- Code follow-ups if live numbers reveal gaps: expansion prompt tuning, fuzzy-match threshold, expected-POI list adjustments (e.g. Griffith Observatory may legitimately show up for RF-009 movie studios — decide expected vs off-target before publishing).

### 2. Affiliate tracking on existing deep-links

- **Blocked on founder action**: register for Viator, GetYourGuide, Skyscanner affiliate programs, then supply the IDs.
- Code side is small: append affiliate params to the existing booking deep-links (grep `booking_url` construction + `KAYAK`/`Viator` link builders).

---

## 🔧 Operational / hygiene items

- **E2E of the pinned-POI positive path with real data**: needs `osm_pois` ingested for a destination + a signed-in session. Flow: sign in on local → generate a London trip → Anya: "I'm a huge Harry Potter fan" → confirm 📌 pins with real coords, in-place regeneration, and diff chips. (Negative/degradation path live-verified 2026-07-12; positive path is unit- and eval-proven offline.)
- **Run corpus ingestion once locally** (`chains/itinerary_corpus_extraction_chain.py::ingest_itinerary_corpus()`, needs `GEMINI_API_KEY`) so v10.15's retrieval has data. Same for gem intel (`reddit` + `osm_pois`) and pin verification (`osm_pois`/`wiki`) — all three features currently degrade cleanly to their no-data fallbacks on a fresh `:memory:` Qdrant. (The refinement eval does NOT need this — it seeds its own fixtures.)
- **E2E check of gems in a real generation**: sign in on local, generate a Phuket/Goa trip with crowd dial = Hidden Gems, confirm 💎-tagged items with provenance appear.
- **`WizardForm.tsx` is dead code** (never imported; `LLMWizard` is the live wizard). The crowd-dial UI in `PaceBudgetSection.tsx` is unreachable until that form is revived — decide whether to delete the form wizard or mount it somewhere.
- **Dependabot: google-genai → 2.10.0** is open; when merged, add `ThinkingConfig(thinking_budget=0)` to `interest_expansion_chain.py` (drop cap to ~512) and consider the same for `extract_trip_chain.py`.
- Consider a `HIDDEN_GEM` / `PINNED` metric in admin analytics (how often gems/pins get generated & kept) once real traffic exists.
- Optional eval-harness extension noted in `docs/eval-set.md` §4U: point `run_rag_eval.py` at `retrieve_context()` (with reranking forced on) for full-pipeline retrieval scoring.

## 💰 Deferred by cost decision (revisit later)

- **BestTime.app live crowd-forecast layer** (paid API) — corpus signal shipped first; live layer is a premium/B2B upsell candidate.
- **Booking.com affiliate pricing for accommodation** — blocked on partner-account approval (see TECHNICAL_DOCUMENTATION §14 backlog table).

## 📋 Phase 2 preview (don't start until Phase 1 eval gate passes)

Agent mode (branded PDF export, markup field, client-shareable link) · live budget grounding (Amadeus free tier, IRCTC fare tables) · hand-onboard 10 agents. Full detail + kill/go criteria in [GTM_STRATEGY.md](GTM_STRATEGY.md) §5.
