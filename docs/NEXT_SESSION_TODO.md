# Next-Session TODO — GTM Phase 1 Execution

**Last updated:** 2026-07-13 (end of session, v10.18.2)
**Context:** Executing the Phase 1 roadmap in [GTM_STRATEGY.md](GTM_STRATEGY.md). The kill-criterion gate now has real numbers on all three systems; publishing is blocked on a short recall-bug fix list, then a repeat live run. This file is the pick-up point for the next session.

---

## ✅ Done last session (for context)

1. **First live kill-criterion run + both baselines** (v10.18.1–.2):
   - Live WanderPlanner: **fidelity 0.771, pin recall 0.750, inclusion 0.771, stability 0.812, honesty 4/4**. 13/16 positive cases ≥0.87.
   - **ChatGPT free tier** (founder-recorded): recall 1.000, unverifiable 0.747, honesty 0/4 (suggested the nonexistent "Wizarding World Goa").
   - **Claude Sonnet** (fresh cold-context no-tools agents, method in the baseline file): recall 0.979, unverifiable 0.786, strict honesty 0/4 **but verbally honest on all four** (explicitly said the ask can't be served; raw responses preserved).
   - Verdict shaping up: **the wedge is trust + itinerary follow-through, not recall.**
   - The live run itself caught three production bugs, all fixed + tested (207 passed): a dead `google.api_core` import silently disabling ALL live Gemini generation; no retry on transient 503s in `chat_refine`; a retired preview model id aborting the whole Gemini fallback chain.
   - Eval tooling: `--results` rescore mode, baseline labels, per-case error resilience. Reports in gitignored `eval/out/` (`report_vs_chatgpt.md`, `report_vs_claude_sonnet.md`).

---

## ⏭️ Remaining Phase 1 items (in execution order)

### 1. Fix the three live recall bugs + compliance gap — NEXT UP

From the 2026-07-13 live run (details: TECHNICAL_DOCUMENTATION §14 v10.18.2):

- **RF-004 Kyoto (zen gardens), RF-014 Goa (Portuguese heritage), RF-016 Bengaluru (palaces & gardens) → zero pins.** Diagnose where the live pipeline dropped out: `named_interest` detection in `chat_refine`? expansion returning empty? verification rejecting everything? Prime suspects: **diacritics** (Ryōan-ji vs Ryoan-ji, Sé vs Se — check `poi_pinning._normalize`, which strips non-ASCII to spaces and may break containment matching) and multi-word interest phrasings not being detected. Reproduce cheaply: call `chat_refine`/`expand_interest_to_candidates` live for just those 3 cases before touching code.
- **RF-007 Barcelona: 3 correct pins, only 1 honoured exactly-once with the `pinned` tag** in the generated itinerary — check whether Gemini renamed (Família vs Familia), duplicated, or dropped the tag; consider strengthening the PINNED prompt block or post-generation pin enforcement (deterministic: inject missing pins like `_mock_itinerary` does).
- **RF-001 London pinned distractor Borough Market** — expansion over-reach; tighten the expansion prompt ("only places that specifically serve the interest") and/or drop candidates that match fixtures but not the interest.
- Add offline regression cases for whatever the diagnosis finds (e.g. diacritic name matching tests).

### 2. Repeat the live run → kill/go decision → publish

- `python -m eval.run_refinement_eval --live` (~$0.40), then `--results ... --baseline` for both baselines.
- Expectation after fixes: recall ~0.9+; wedge story: verified-by-construction pins, honest refusals, itinerary follow-through vs 0.75–0.79 unverifiable-suggestion rates.
- **Publish deliberately**: commit the two reports out of `eval/out/` + write the public comparison piece. Must state the Claude verbal-honesty nuance and the recording protocol (both baseline files document it) — credibility depends on not overclaiming.
- This is the GTM §5 kill/go gate: if fixed-recall still can't support the trust story vs ChatGPT, pivot per strategy.

### 3. Affiliate tracking on existing deep-links

- **Blocked on founder action**: register for Viator, GetYourGuide, Skyscanner affiliate programs, then supply the IDs.
- Code side is small: append affiliate params to the existing booking deep-links (grep `booking_url` construction + `KAYAK`/`Viator` link builders).

---

## 🔧 Operational / hygiene items

- **GEMINI_MODEL note:** local `.env` still says `gemini-2.5-flash-lite`, which was heavily 503-congested on 2026-07-13; the live eval ran with a process-level `GEMINI_MODEL=gemini-2.5-flash` override. Consider switching the default (or trust the now-fixed fallback chain).
- **E2E of the pinned-POI positive path with real data**: needs `osm_pois` ingested for a destination + a signed-in session (eval fixtures don't cover the real-ingestion path). Flow: sign in on local → London trip → Anya: "I'm a huge Harry Potter fan" → confirm 📌 pins, in-place regeneration, diff chips.
- **Run corpus ingestion once locally** (`ingest_itinerary_corpus()`, needs `GEMINI_API_KEY`) so v10.15 retrieval, gem intel and pin verification have real data (all three degrade cleanly today on empty Qdrant).
- **E2E check of gems in a real generation** (crowd dial = Hidden Gems → 💎 items with provenance).
- **`WizardForm.tsx` is dead code** (`LLMWizard` is live) — decide delete vs mount; crowd-dial UI in `PaceBudgetSection.tsx` unreachable until then.
- **Dependabot: google-genai → 2.10.0**: when merged, add `ThinkingConfig(thinking_budget=0)` to `interest_expansion_chain.py` (cap back to ~512) and consider same for `extract_trip_chain.py`.
- `HIDDEN_GEM`/`PINNED` admin metrics once real traffic exists · optional §4U extension: point `run_rag_eval.py` at `retrieve_context()`.

## 💰 Deferred by cost decision (revisit later)

- **BestTime.app live crowd-forecast layer** (paid API) — premium/B2B upsell candidate.
- **Booking.com affiliate pricing for accommodation** — blocked on partner-account approval.

## 📋 Phase 2 preview (don't start until Phase 1 eval gate passes)

Agent mode (branded PDF export, markup field, client-shareable link) · live budget grounding (Amadeus free tier, IRCTC fare tables) · hand-onboard 10 agents. Full detail + kill/go criteria in [GTM_STRATEGY.md](GTM_STRATEGY.md) §5.
