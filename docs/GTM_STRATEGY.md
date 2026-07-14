# WanderPlanner — GTM Strategy & Product Roadmap

**Date:** 2026-07-11
**Status:** Active plan
**Inputs:** [STARTUP_EVALUATION.md](STARTUP_EVALUATION.md) (+ 2026-07-11 addendum), first user interviews (July 2026), live market research (sources at end)
**Owner:** Solo founder, nights-and-weekends; plan is sized accordingly

---

## 1. Core thesis

The moat is **not** the chatbot, the voice UX, or any single feature — all replicable by a funded competitor in a sprint. The moat is three compounding assets:

1. **A proprietary, verified India-context corpus** — hidden-gem POIs scored from Reddit signal, verified against OSM; grounded India cost data (trains, veg meals, family math) no global player models.
2. **Measurable personalization fidelity** — published evals proving WanderPlanner itineraries respond to constraints ("I'm a Harry Potter fan", "less crowded beaches") when ChatGPT/Gemini output doesn't.
3. **Distribution in a channel funded players ignore** — India's offline travel agents.

User feedback (July 2026) was not "add features" — it was "make the intelligence real." The three complaints (touristy output, refinements don't bite, shallow budgets) share one root cause: generation is prompt-led, and the data that fixes it is built but unwired (`itinerary_corpus` is ingest-only as of this writing).

---

## 2. Product bets (mapped to user feedback)

### Bet 1 — Crowd-aware planning ("hidden gems")

Generic LLMs regurgitate top-10 lists — a structural weakness of every ChatGPT-wrapper competitor. The Reddit corpus already contains the antidote.

- **Gem scoring:** rank POIs by high sentiment × low mention volume in the Reddit corpus (a beach praised in 4 comments = gem signal; one appearing in 400 = crowd signal). Verify every candidate against OSM so a hallucinated place never ships.
- **Crowd dial in the wizard:** Touristy ↔ Balanced ↔ Off-beat, a first-class preference alongside budget tier.
- **Optional live layer:** crowd forecasts for top venues via BestTime.app foot-traffic API / Google Popular Times.
- **Provenance UI:** "Recommended by 6 travellers on r/phuket" — the receipts are what make it believable and shareable.

### Bet 2 — Refinements as hard constraints (the "Harry Potter test")

1. **Interest → entity expansion chain:** named interest → candidate POIs (WB Studio Tour Leavesden, Bodleian Divinity School, Christ Church Great Hall, Platform 9¾, Alnwick Castle).
2. **Verification:** each candidate geocoded/confirmed via OSM/Wikivoyage before use.
3. **Hard pinning:** survivors become must-include constraints in generation — not prompt suffixes.
4. **Visible diff after every refinement:** "Added: WB Studio Tour (Day 3) · Swapped: Oxford walking tour → Bodleian tour." If the user can't see the change, it didn't happen.
5. **Refinement-fidelity eval suite** built on the existing `docs/eval-set.csv`: ~20 named-interest prompts scored on whether the right POIs appear. Publish "WanderPlanner vs ChatGPT" results — this is marketing, not just QA.

### Bet 3 — Grounded, inverse-plannable budgets

For Indian users budget is *the* planning primitive, not a filter.

- **Live grounding of big-ticket items:** flights via Amadeus Self-Service (free tier) or Skyscanner affiliate API; hotel medians per city/tier via Booking affiliate data; **train fares from IRCTC fare tables (deterministic — a uniquely Indian data advantage no global competitor models).**
- **Confidence bands, not point estimates:** "₹72k–₹85k; flights are 40% of it and rising — book by Aug 2."
- **Inverse planning mode:** "Best 6-day trip for a family of 4 under ₹1L" — start from the budget, derive destination + itinerary.
- Per-day burn view; existing splurge/save preferences allocate the delta.

---

## 3. Market landscape (verified July 2026)

| Fact | Implication |
|---|---|
| **Mindtrip acquired Thatch (2025)** — the creator-itinerary marketplace, $5.2M raised, still had to sell | The influencer-marketplace model is owned by the best-funded competitor; a solo clone faces two-sided cold start against an incumbent. **Do not build it.** |
| Global white-label B2B exists: mTrip (300+ agencies, 35 countries), Sygic, Simplified.Travel | Model is proven; none are India-native |
| Sembark: 1,000+ Indian travel businesses paying for CRM + drag-and-drop itinerary builder; TravClan: 15,000+ agents (inventory-led) | **Indian agents pay for software.** Neither product is AI-native — no generative itineraries, no Hinglish conversation, no gem/budget intelligence. This is the open wedge. |
| Travel VC rotated B2B > B2C (2024, first time); Vacay.io (free consumer AI planner) shut down | B2B revenue is the fundable, survivable path in this category |

---

## 4. GTM verdicts

| Option | Verdict | Reasoning |
|---|---|---|
| Affiliate links only | **Turn on now; not a strategy** | Near-zero effort, real conversion signal; meaningless without traffic. It's a monetization layer, not a GTM. |
| B2B embed in large travel portals | **Later, opportunistic** | MMT/Yatra won't procure from a solo founder. A smaller OTA or one state tourism board deal = credibility; expect long sales cycles. |
| **Offline travel agents ("Anya for Agents")** | **★ Primary revenue engine** | Lakhs of Indian agents; itinerary creation is their daily time-sink; Sembark proves willingness to pay; nobody sells them AI-native generation. |
| Influencer itinerary marketplace | **Don't build the marketplace** | Mindtrip/Thatch owns the model. Instead: license creator itineraries **into the corpus** with attribution + rev-share — creators become data supply and distribution without marketplace cold-start. |

### Anya for Agents — the offering

An agent copilot that turns a WhatsApp-style Hinglish conversation into a **branded, costed, PDF-ready itinerary in ~5 minutes** (vs. hours in templates). Crowd dial + grounded budget math are the demo-wow.

- **Pricing:** ₹1,500–3,000/month/seat (Sembark-adjacent).
- **Channels:** TAAI/TAFI chapters, agent WhatsApp communities, travel trade shows (OTM Mumbai, SATTE Delhi).
- **Consumer app's role:** validation lab, eval showcase, SEO/content engine. Same backend serves both surfaces — every intelligence improvement ships to both.

---

## 5. Roadmap with kill/go criteria

### Phase 1 — Prove the wedge (months 0–3)

| # | Item | Notes | Status |
|---|---|---|---|
| 1 | **Wire `itinerary_corpus` retrieval into generation** | The biggest pending unlock; ingestion already ships | ✅ Done (v10.15, 2026-07-11) |
| 2 | Hidden-gem scoring + crowd dial | Reddit signal × OSM verification | ✅ Done (v10.16, 2026-07-11) — BestTime live-crowd layer deferred (paid API) |
| 3 | Refinement hard-constraints + visible diff UI | Interest→entity→verify→pin pipeline | ✅ Done (v10.17, 2026-07-12) — pins verified vs OSM/wiki, hard-pinned in the prompt, in-place regeneration + diff chips in Anya panel |
| 4 | Refinement-fidelity eval suite; publish vs-ChatGPT results | Builds on `docs/eval-set.csv` | ✅ Done (v10.20.0, 2026-07-14) — clean live run: fidelity **0.975**, recall 0.938, inclusion/stability **1.000**, honesty 4/4 (RF-010 recovered from the transient 503s; RF-012 improved to 0.67 untouched). **Published** in `docs/eval-results/`: comparison piece + both verbatim reports, with the Claude verbal-honesty disclosure, the recording protocol, and a "what we are NOT claiming" section. Founder to adapt for external channels |
| 5 | Turn on affiliate tracking on existing deep-links | Viator / GetYourGuide / Skyscanner | Pending — blocked on founder affiliate-program registrations. Link formats fixed in v10.20.0 (audit §1.2): Google Flights on supported `?q=` syntax, Skyscanner/MMT on IATA deep-links via static city-code map with honest search-page fallback — affiliate params can now be appended to working links |

**Kill criterion:** if the fidelity evals can't measurably beat ChatGPT, the consumer differentiation story is dead → go pure B2B tooling.

### Phase 2 — First revenue (months 3–6)

| # | Item | Notes |
|---|---|---|
| 1 | Agent mode: branded PDF export, agent markup/margin field, client-shareable link | Thin layer over existing generation |
| 2 | Live budget grounding (flights, IRCTC trains, hotel medians) + confidence bands | Amadeus free tier / affiliate APIs |
| 3 | Hand-onboard 10 agents free → convert 5 to paid | Direct outreach via agent communities |

**Go criterion:** 5 paying agents → build multi-tenant. **Kill criterion:** 0 conversions after 25 demos → agent thesis wrong; pivot to tourism-board pilots.

### Phase 3 — Scale the channel (months 6–12)

- Embeddable widget/API (Simplified.Travel model, India-priced).
- One state tourism board pilot (credibility anchor).
- Creator-itinerary licensing into the corpus (attribution + rev-share).
- Revisit consumer premium (₹99/mo: unlimited refinements + live budget alerts) **only after** B2B revenue exists.

---

## 6. What we deliberately do NOT do

- Build a creator marketplace (contested, cold-start, capital-intensive).
- Add breadth features (calendar sync, more personas, social) before Phase 1 evals exist.
- Chase large-OTA embed deals before having agent revenue and a tourism-board logo.
- Consumer subscriptions before B2B revenue — the category's graveyard (Vacay.io) is consumer-first free planners.

---

## Sources

- Mindtrip–Thatch acquisition: [PhocusWire](https://www.phocuswire.com/mindtrip-thatch-merge-ai-travel-planning-creators); Thatch funding: [Crunchbase](https://www.crunchbase.com/organization/nat) — verified 2026-07-11
- White-label B2B: [mTrip](https://www.mtrip.com/), [Sygic](https://www.sygic.com/press/sygic-travel-releases-white-label-travel-planner-for-b2b-customers), [Simplified.Travel](https://www.simplified.travel/) — verified 2026-07-11
- India agent SaaS: [Sembark](https://sembark.com/) (1,000+ businesses), [TravClan](https://www.travclan.com/) (15,000+ agents) — verified 2026-07-11
- Crowd data: [BestTime.app](https://besttime.app/) foot-traffic API — verified 2026-07-11
- B2B>B2C travel funding rotation, Vacay.io shutdown: see [STARTUP_EVALUATION.md](STARTUP_EVALUATION.md) sources
