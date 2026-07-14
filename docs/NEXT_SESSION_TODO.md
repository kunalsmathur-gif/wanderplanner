# Next-Session TODO — GTM Phase 1 Execution

**Last updated:** 2026-07-13 (end of session, v10.19.0)
**Context:** Executing the Phase 1 roadmap in [GTM_STRATEGY.md](GTM_STRATEGY.md). The recall bugs are fixed and the repeat live run scored **fidelity 0.904 / honesty 4-4** — the kill-criterion gate passes on numbers. Publishing needs one clean rerun (RF-010 was zeroed by transient Gemini 503s). A full UI/UX + copy audit was completed (findings below, **no changes made yet** — founder to prioritise).

---

## ✅ Done last session (for context)

1. **Three zero-pin recall bugs diagnosed + fixed** (v10.19.0): root cause was named-interest **detection**, not diacritics — Gemini routed "zen gardens"/"Portuguese colonial heritage" into `themes` patches and answered the Bengaluru question conversationally. Fixes: broadened detection prompt (any concrete interest + question phrasings), deterministic themes-patch backstop in `_apply_interest_pinning`, NFKD diacritic folding in `_normalize`, and exact>containment>fuzzy `_best_osm_match` (live repro caught "Ginkaku-ji" being pinned as "Kinkaku-ji" via first-fuzzy-hit).
2. **Pin inclusion made structural** (`itinerary_chain._enforce_pins`): tag repair, duplicate untagging, dropped-pin injection after generation on every path. Live inclusion/stability now 1.00 on every pinned case.
3. **Expansion prompt**: anti-distractor rule (RF-001 Borough Market) + heritage-quarter allowance (RF-014 Fontainhas).
4. **Repeat live run**: fidelity 0.904 · recall 0.854 · inclusion 0.938 · stability 0.938 · precision 0.917 · honesty 4/4. Both baseline reports regenerated in `eval/out/`. 219 unit tests pass; offline gate 1.000.

## ⏭️ Remaining Phase 1 items (in execution order)

### 1. One clean live rerun, then publish — NEXT UP

- **RF-010 Singapore scored 0.00 purely from persistent Gemini 503s** during expansion (log line: "interest expansion failed for 'hawker centres'"). Rerun `python -m eval.run_refinement_eval --live` (~$0.40, `GEMINI_MODEL=gemini-2.5-flash` process override) at a less congested hour; expect recall ≈0.90+.
- Optional recall chase before publishing: **RF-012 Mumbai (0.33)** — live expansion proposed Film City but not Mannat/Prithvi Theatre; consider whether the tightened anti-distractor rule is now too conservative for celebrity-home/theatre venues, or accept and disclose.
- Then `--results ... --baseline` for both baselines and **publish deliberately**: commit the two reports out of gitignored `eval/out/` + write the comparison piece. Must state the Claude verbal-honesty nuance and the recording protocol — credibility depends on not overclaiming.

### 2. UI/UX + copy audit follow-ups (2026-07-13 audit — identified only, NOT yet fixed; founder to prioritise)

Full audit with file-level detail and suggested fix order: [UI_UX_AUDIT_2026-07-13.md](UI_UX_AUDIT_2026-07-13.md). Summary:

**Trust-critical (fix before any public push — they contradict the verified-truth wedge):**
- `routers/travel_tips.py` — the Gemini prompt generates tips that *"read like they come from real travelers"* and labels them `r/travel` / `TripAdvisor` / `Lonely Planet` / `Nomadic Matt`; `_fallback_tips` hardcodes fake upvote counts (127/94/156/203). **Fabricated provenance on a production surface.** Real Reddit tips (also fetched) are fine — label LLM/fallback tips honestly ("General tip") or drop them.
- Booking deep-links likely broken: Google Flights uses the retired `#search;f=...` fragment syntax (opens bare homepage); Skyscanner/MakeMyTrip URL templates expect IATA/city codes but receive raw city names. The sidebar promises "Links open pre-filled with your trip details." Affiliate tracking (item 3 below) builds on these — fix formats first.

**High (visible polish/correctness):**
- Dark mode gaps — hardcoded light-only styling in `ItineraryOverview.tsx:66`, `ExpenseBreakupCard.tsx:39`, `FeasibilityCard.tsx:124`, `BookingLinksSection.tsx:162`, `PdfDownloadButton.tsx` (slate-100/200), `ErrorState.tsx` (also uses the OLD `#1E40AF` palette, not `--_primary`).
- Developer-speak in user-facing errors: "Check that the backend is running and retry" (`ErrorState.tsx:19`), "please make sure the backend is running" (`ConversationalWizard.tsx:1270`).
- `PDFDownloadLink` renders the PDF document eagerly on every dashboard mount (CPU cost on load) — switch to on-demand generation.
- Raw ISO dates in UI: day tabs (`ItineraryTimeline.tsx:190`) and share page show `2026-11-14` instead of "Fri, 14 Nov".
- Currency display inconsistent: metrics show `INR 150,000` (`Column1Metrics.tsx:63`) vs landing's `₹1,50,000` (Indian grouping); pick one formatter app-wide.
- `CurrencyWidget` surfaces raw "Currency rates unavailable." in the sidebar — degrade silently or soften copy.

**Medium (a11y + metadata):**
- `/login`, `/signup`, `/account`, share page don't set per-page `<title>`/metadata (all render the landing title; hurts SEO + tab identification). Share page (`/t/[slug]`) is client-fetched — no OG tags, so shared links unfurl blank in WhatsApp/Slack; it's a growth surface, consider SSR + OG image.
- Unnamed icon-only buttons (no aria-label): currency refresh (`Column1Metrics` area), BookingHub tab buttons, `/dev` page cards.
- Share page doesn't render 📌 pinned / 💎 gem badges — the differentiating features are invisible on the viral surface.
- Mock/dev YouTube link is a rickroll (`dev/mockData.ts`, `dQw4w9WgXcQ`) — harmless in dev, embarrassing if mock path ever serves prod.

**Verified OK (no action):** mobile bottom-tab layout (Itinerary/Overview/Map & Tips, no horizontal overflow), landing copy + FAQ, wizard conversational flow + chips, account page (delete confirmation done right), share-page expired-link state, PolaroidCard theming (an automation-pane artifact initially looked like a dark-mode bug — it isn't one).

### 3. Affiliate tracking on existing deep-links

- **Blocked on founder action**: register for Viator, GetYourGuide, Skyscanner affiliate programs, then supply the IDs.
- Code side is small: append affiliate params to the booking deep-links — but fix the broken link formats (audit item above) first.

## 🔧 Operational / hygiene items

- **GEMINI_MODEL note:** local `.env` still says `gemini-2.5-flash-lite` (503-congested on 2026-07-13 again); both live evals ran with process-level `GEMINI_MODEL=gemini-2.5-flash`. Consider switching the default.
- **E2E of the pinned-POI positive path with real data**: needs `osm_pois` ingested + signed-in session. Flow: sign in → London trip → Anya: "I'm a huge Harry Potter fan" → confirm 📌 pins, in-place regeneration, diff chips. (The v10.19 themes-backstop path could also be E2E'd: "add some zen gardens to my trip".)
- **Run corpus ingestion once locally** (`ingest_itinerary_corpus()`, needs `GEMINI_API_KEY`) so v10.15 retrieval, gem intel and pin verification have real data.
- **E2E check of gems in a real generation** (crowd dial = Hidden Gems → 💎 items with provenance).
- **`WizardForm.tsx` is dead code** (`LLMWizard` is live) — decide delete vs mount; crowd-dial UI in `PaceBudgetSection.tsx` unreachable until then. (Old wizard sections also carry the pre-rebrand `#1E40AF` palette — deleting them shrinks the dark-mode fix surface.)
- **Dependabot: google-genai → 2.10.0**: when merged, add `ThinkingConfig(thinking_budget=0)` to `interest_expansion_chain.py` (cap back to ~512) and consider same for `extract_trip_chain.py`.
- `HIDDEN_GEM`/`PINNED` admin metrics once real traffic exists · optional §4U extension: point `run_rag_eval.py` at `retrieve_context()`.

## 💰 Deferred by cost decision (revisit later)

- **BestTime.app live crowd-forecast layer** (paid API) — premium/B2B upsell candidate.
- **Booking.com affiliate pricing for accommodation** — blocked on partner-account approval.

## 📋 Phase 2 preview (don't start until Phase 1 publish is done)

Agent mode (branded PDF export, markup field, client-shareable link) · live budget grounding (Amadeus free tier, IRCTC fare tables) · hand-onboard 10 agents. Full detail + kill/go criteria in [GTM_STRATEGY.md](GTM_STRATEGY.md) §5.
