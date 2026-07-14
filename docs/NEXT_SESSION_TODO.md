# Next-Session TODO — GTM Phase 1 wrap-up → Phase 2

**Last updated:** 2026-07-14 (end of session, v10.20.0)
**Context:** Phase 1 item 4 is **done and published**: the clean live rerun scored **fidelity 0.975 / recall 0.938 / inclusion+stability 1.000 / honesty 4-4**, and the comparison piece + both baseline reports now live in [docs/eval-results/](eval-results/README.md) (with the Claude verbal-honesty disclosure and the recording protocol). The two trust-critical audit items are fixed. Remaining Phase 1 surface is the rest of the UI/UX audit + the founder-blocked affiliate item.

---

## ✅ Done last session (for context)

1. **Clean live rerun (2026-07-14, gemini-2.5-flash):** fidelity 0.975 · recall 0.938 · inclusion 1.000 · stability 1.000 · precision 0.979 · honesty 4/4. RF-010 Singapore 0.00 → 1.00 (transient-503 diagnosis confirmed); RF-012 Mumbai 0.33 → 0.67 with no code change. Remaining recall misses: RF-001 London / RF-009 LA / RF-012 Mumbai, all 0.67 (expansion doesn't propose one truth-set place each).
2. **Published `docs/eval-results/`:** comparison piece ("Can your AI travel planner prove it listened?") + verbatim reports vs ChatGPT and vs Claude Sonnet, dated 2026-07-14. Piece includes recording protocol, the mandatory Claude verbal-honesty disclosure, and a "what we are NOT claiming" section. **Founder action: adapt/post externally** (blog, r/travel, IH — GTM §6).
3. **Trust-critical audit fixes (v10.20.0):**
   - `travel_tips.py` — fabricated provenance removed; "General tip" labelling enforced in code (source/score/post_url overridden regardless of model output); 4 new unit tests lock the rule; frontend renders no-URL tips as plain cards.
   - Booking deep-links — Google Flights on supported `?q=` natural-language format; NEW `lib/cityCodes.ts` (~75-city static IATA map) gives Skyscanner/MMT real deep-links (verified: `del/tyo/261114/261116`, `DEL-TYO-14/11/2026_TYO-DEL-16/11/2026`, correct `intl` flag) with honest search-page fallback + dynamic sidebar copy when codes/dates are missing.
   - Dev fixture now seeds Delhi origin + real dates (prefill path exercisable locally); rickroll mock id removed (audit §3.4).
4. 223 unit tests pass · tsc clean · eval rescore label no longer nests.

## ⏭️ Remaining items (in suggested order)

### 1. UI/UX audit follow-ups — remaining items ([UI_UX_AUDIT_2026-07-13.md](UI_UX_AUDIT_2026-07-13.md))

§1.1/§1.2/§3.4 are done. Suggested fix order from the audit:

- **§2.1 dark-mode gaps + §2.2 error copy** as one polish pass: `ItineraryOverview.tsx:66`, `ExpenseBreakupCard.tsx:39`, `FeasibilityCard.tsx:124`, `BookingLinksSection.tsx` (tabs/cards still `#1E40AF`/light-only), `PdfDownloadButton.tsx`, `ErrorState.tsx` (old palette + "backend is running" copy; also `ConversationalWizard.tsx:1270`). Deleting dead `WizardForm.tsx` first shrinks the surface (old wizard sections carry the pre-rebrand palette).
- **§2.3–§2.5**: on-demand PDF generation (`pdf().toBlob()` on click), human dates ("Fri, 14 Nov") in day tabs + share page, one `Intl.NumberFormat('en-IN')` currency formatter app-wide, soften `CurrencyWidget` failure copy, clarify BestTime "Peak" vs "Best" labels.
- **§3.2 share-page SSR + OG tags** (own milestone — the viral surface unfurls blank in WhatsApp/Slack; 📌/💎 badges also missing there).
- **§3.1/§3.3**: per-page `<title>`/metadata for `/login` `/signup` `/account` `/t/[slug]`; aria-labels for icon-only buttons.

### 2. Optional eval recall chase (only if publishing follow-ups need it)

RF-001/RF-009/RF-012 all miss on the same mode: interest expansion not proposing one truth-set place. The anti-distractor rule may be too conservative for celebrity-home/theatre venues (Mannat, Prithvi Theatre). Decide: tune expansion or accept + already-disclosed. Any change = rerun live (~$0.40) before touching the published numbers.

### 3. Affiliate tracking — blocked on founder

Register Viator / GetYourGuide / Skyscanner affiliate programs and supply IDs. Link formats are now fixed (v10.20.0), so the code side is a small param-append in `BookingLinksSection.tsx` + `cityCodes.ts` coverage check.

## 🔧 Operational / hygiene items (carried over)

- **GEMINI_MODEL:** local `.env` still `gemini-2.5-flash-lite` (503-congested repeatedly); live evals use process-level `gemini-2.5-flash`. Consider switching the default.
- **E2E pinned-POI positive path with real data** (needs `osm_pois` ingested + signed-in session): London trip → "I'm a huge Harry Potter fan" → 📌 pins, in-place regen, diff chips. Also the themes-backstop path ("add some zen gardens to my trip").
- **Corpus ingestion once locally** (`ingest_itinerary_corpus()`, needs `GEMINI_API_KEY`) for v10.15 retrieval/gem intel/pin verification with real data.
- **E2E gems check** (crowd dial = Hidden Gems → 💎 with provenance).
- **`WizardForm.tsx` dead code** — decide delete vs mount (crowd-dial UI in `PaceBudgetSection.tsx` unreachable until then).
- **Dependabot google-genai → 2.10.0**: when merged, add `ThinkingConfig(thinking_budget=0)` to `interest_expansion_chain.py` (cap back to ~512); consider same for `extract_trip_chain.py`.
- `HIDDEN_GEM`/`PINNED` admin metrics once real traffic exists · optional §4U: point `run_rag_eval.py` at `retrieve_context()`.
- Windows gotcha: `git commit -m` with embedded double quotes breaks in PowerShell 5.1 — write message to a file, use `git commit -F`.

## 💰 Deferred by cost decision (revisit later)

- **BestTime.app live crowd-forecast layer** (paid API) — premium/B2B upsell candidate.
- **Booking.com affiliate accommodation pricing** — blocked on partner approval.

## 📋 Phase 2 preview (publish is done — Phase 2 can start once founder signs off on the piece)

Agent mode (branded PDF export, markup field, client-shareable link) · live budget grounding (Amadeus free tier, IRCTC fare tables) · hand-onboard 10 agents. Full detail + kill/go criteria in [GTM_STRATEGY.md](GTM_STRATEGY.md) §5.
