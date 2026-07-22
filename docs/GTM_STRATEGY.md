# WanderPlanner — GTM Strategy & Product Roadmap

**Date:** 2026-07-11
**Status:** Active plan
**Inputs:** [STARTUP_EVALUATION.md](STARTUP_EVALUATION.md) (+ 2026-07-11 addendum), first user interviews (July 2026), live market research (sources at end)
**Owner:** Solo founder, nights-and-weekends; plan is sized accordingly

---

## 1. Core thesis

The moat is **not** the chatbot, the voice UX, or any single feature — all replicable by a funded competitor in a sprint. The moat is three compounding assets:

1. **A proprietary, verified India-context corpus** — hidden-gem POIs scored from Reddit + (planned) YouTube comment signal, verified against OSM; grounded India cost data (trains, veg meals, family math) no global player models. Reddit ingestion is currently blocked in prod (403s, approval pending) — see item 2 below and `docs/NEXT_SESSION_TODO.md` for the multi-source diversification plan that keeps this bet alive independent of Reddit's approval status.
2. **Measurable personalization fidelity** — published evals proving WanderPlanner itineraries respond to constraints ("I'm a Harry Potter fan", "less crowded beaches") when ChatGPT/Gemini output doesn't.
3. **Distribution in a channel funded players ignore** — India's offline travel agents.

User feedback (July 2026) was not "add features" — it was "make the intelligence real." The three complaints (touristy output, refinements don't bite, shallow budgets) share one root cause: generation is prompt-led, and the data that fixes it is built but unwired (`itinerary_corpus` is ingest-only as of this writing).

---

## 2. Product bets (mapped to user feedback)

### Bet 1 — Crowd-aware planning ("hidden gems")

Generic LLMs regurgitate top-10 lists — a structural weakness of every ChatGPT-wrapper competitor. The Reddit corpus already contains the antidote — though Reddit ingestion is currently broken in production (403s since the Cloud migration, formal API approval pending, no ETA); a YouTube Data API v3 comment-mining source is planned to keep this bet shipping regardless of that approval's outcome (see `docs/NEXT_SESSION_TODO.md`).

- **Gem scoring:** rank POIs by high sentiment × low mention volume, blended across the Reddit corpus and (planned) YouTube comment threads (a beach praised in 4 mentions = gem signal; one appearing in 400 = crowd signal). Verify every candidate against OSM so a hallucinated place never ships. A composite authenticity weight (account/channel age, engagement corroboration, temporal-clustering and duplicate-text penalties) is planned to prevent low-volume-but-fake signal (e.g. paid reviews) from being mistaken for a genuine hidden gem — see `docs/NEXT_SESSION_TODO.md`.
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

> **Shipped today vs. this bet's paid-API vision:** the bullets above (Amadeus/Skyscanner/Booking/IRCTC) describe the target end-state once paid live-pricing APIs are wired in — not yet built. What's actually live today is a **free-tools, deterministic estimator** (`core/budget_estimator.py`) that already delivers the core "grounded, not guessed" positioning without any paid API: flights use real haversine distance between the user's two cities mapped to a fare band; stay/food first try a real median price mined from the app's own pre-scraped RAG corpus (Wikivoyage/Reddit/YouTube-comment mentions for that exact destination) before falling back to a hand-authored, research-anchored flat table. The discipline that matters for the pitch: **if no real data is found for a destination, the code says so and falls back rather than letting the LLM invent a number** — the same "honest about what it doesn't know" positioning this bet is selling, already true pre-revenue. This is the free-tier proof point this bet's paid-API roadmap upgrades from, not a placeholder to be embarrassed about. Full mechanism explainer in `docs/PRD.md`'s R5 section and `docs/DEMO_DAY_FAQ_CHEATSHEET.md` Q14.

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

### Consumer → agent hook (the bridge between the two surfaces)

The consumer app's real job isn't just SEO/eval showcase — it's the **top of the agent-lead funnel**. Once an itinerary is generated, add a contextual CTA — **"Get This Itinerary Booked by a Local Expert"** — placed alongside the existing OTA deep-link section (`BookingLinksSection.tsx`), not a disruptive modal. Deliberately not framed as "request a quotation": that reads cold/transactional and implies price uncertainty right at the moment trust in the plan is highest.

- **Best mode of contact: WhatsApp**, not a form-then-email flow — `wa.me/<agent_number>?text=<prefilled itinerary summary>` (destination, dates, pax, budget tier, shareable itinerary link). Matches where Indian users and offline agents already operate; a generic web form loses this audience.
- **Implementation shape:** new `AgentHandoffCard.tsx` component (same pattern as `BookingLinksSection.tsx`) + `POST /api/agent-leads` (destination, trip config, contact info → `agent_leads` table) + simple destination-based round-robin routing to onboarded paying agents. **Don't build automated matching before there's real agent supply** — Phase 1 routes to a single manually-handled concierge number or the initial 5 hand-onboarded agents; automate only once the Phase 2 go-criterion (5 paying agents) is hit.
- **Incentive fit:** this is what makes an agent's ₹1,500–3,000/seat feel like more than "faster drafting software" — it's warm consumer demand bundled into (or later, monetized alongside) the subscription, a differentiator neither Sembark nor TravClan offers.
- **Metrics to add to the existing admin dashboard** (same pattern as Gemini/Pexels usage tracking): CTA click-through rate, lead → agent-response rate, lead → booked-trip conversion.

### White-label vs. co-branded — decision for the agent product

**Default to white-label, tiered by price — not a permanent co-brand.** An agency's own customer needs to trust the agency, not an unfamiliar SaaS name riding along on their itinerary PDF; visible WanderPlanner branding on agency output subtly plants "this could be self-served next time," which undercuts the exact trust the agency is paying to project. This isn't a novel risk — it's the reason mTrip (300+ agencies, 35 countries), Sygic, and Simplified.Travel are all white-label B2B; the gap is India-native execution, not the format.

- **Tier 1 (base subscription, ~₹1,500/mo):** agency logo + brand colors on the PDF export (extend the existing `react-pdf` design-token system) and shareable link page; keep only a small "Powered by WanderPlanner AI" footer tag — standard, low-cost, doesn't materially break agency trust.
- **Tier 2 (premium seat, unlocked once the 5-paying-agent go-criterion is hit):** true white-label — zero attribution anywhere, optional custom subdomain (`plans.youragencyname.com`) — a natural, proven upsell lever (same "remove our branding" economics as Shopify apps/Intercom/Calendly) at the top of the existing ₹1,500–3,000 pricing band.
- **Consumer app stays 100% WanderPlanner-branded** regardless — white-labeling only applies to the B2B "Anya for Agents" surface and its outputs, so the consumer brand/lead-gen engine isn't fragmented.
- **Don't build the full white-label engine (custom domains, zero-attribution theming) before Phase 2's paying-agent validation** — the tiered approach lets the base tier ship cheaply now while holding the expensive version for proven demand.

---

## 5. Roadmap with kill/go criteria

### Phase 1 — Prove the wedge (months 0–3)

| # | Item | Notes | Status |
|---|---|---|---|
| 1 | **Wire `itinerary_corpus` retrieval into generation** | The biggest pending unlock; ingestion already ships | ✅ Done (v10.15, 2026-07-11) |
| 2 | Hidden-gem scoring + crowd dial | Reddit signal × OSM verification | ✅ Done (v10.16, 2026-07-11) — BestTime live-crowd layer deferred (paid API). ⚠️ Reddit ingestion currently down in prod (403s, approval pending); multi-source diversification (YouTube comments now, Google Places/TripAdvisor on roadmap) planned to de-risk this bet — see `docs/NEXT_SESSION_TODO.md` |
| 3 | Refinement hard-constraints + visible diff UI | Interest→entity→verify→pin pipeline | ✅ Done (v10.17, 2026-07-12) — pins verified vs OSM/wiki, hard-pinned in the prompt, in-place regeneration + diff chips in Anya panel |
| 4 | Refinement-fidelity eval suite; publish vs-ChatGPT results | Builds on `docs/eval-set.csv` | ✅ Done (v10.20.0, 2026-07-14 → v10.23.0, 2026-07-15) — clean live run: fidelity **0.975**, recall 0.938, inclusion/stability **1.000**, honesty 4/4 (RF-010 recovered from the transient 503s; RF-012 improved to 0.67 untouched). Anti-distractor rule in `interest_expansion_chain.py` tuned to allow famous theatres/walk-of-fame monuments/celebrity residences as "specific" (was silently dropping true positives like Hollywood Walk of Fame, Prithvi Theatre); rerun 2026-07-15: fidelity **0.983** (+0.008), recall **0.958** (+0.020), inclusion/stability still **1.000**, honesty still 4/4 — **improvement confirmed, no regressions** (offline gate unaffected at 1.000, full backend suite green, 3-way manual re-probe validation before publishing). **Published** in `docs/eval-results/`: comparison piece + both dated verbatim report sets (2026-07-14 and 2026-07-15), with the Claude verbal-honesty disclosure, the recording protocol, and a "what we are NOT claiming" section. Founder to adapt for external channels |
| 5 | Turn on affiliate tracking on existing deep-links | Viator / GetYourGuide / Skyscanner | Pending — blocked on founder affiliate-program registrations. Link formats fixed in v10.20.0 (audit §1.2): Google Flights on supported `?q=` syntax, Skyscanner/MMT on IATA deep-links via static city-code map with honest search-page fallback — affiliate params can now be appended to working links |
| 6 | Eval infrastructure hardening: wizard-flow harness, LLM-as-judge quality metric, baseline/candidate compare + failure-clustering tools | Internal QA rigor underpinning the fidelity-eval trust claims above; see `docs/eval-set.md` §7 and `docs/system-design.md` §15A | ✅ Done (2026-07-18) — `eval/run_wizard_eval.py` closes the gap the fidelity suite didn't cover (multi-turn Anya wizard, not just refinement); `eval/judge_metrics.py` adds a subjective tone/personalization/coherence score alongside the existing deterministic accuracy/hallucination metrics in the model-comparison harness (the same harness that will produce future "vs ChatGPT/Claude" numbers); `eval/compare_results.py` + `eval/analyze_results.py` make baseline-vs-candidate regression checks and failure clustering routine instead of manual, so future published comparisons are backed by a repeatable, auditable process |

**Kill criterion:** if the fidelity evals can't measurably beat ChatGPT, the consumer differentiation story is dead → go pure B2B tooling.

### Phase 2 — First revenue (months 3–6)

| # | Item | Notes |
|---|---|---|
| 1 | Agent mode: branded PDF export, agent markup/margin field, client-shareable link | Thin layer over existing generation |
| 2 | Live budget grounding (flights, IRCTC trains, hotel medians) + confidence bands | Amadeus free tier / affiliate APIs. Interim step (v10.28, pre-affiliate-API): hand-authored `distance_pricing.py` bands recalibrated against 3 real fare screenshots (near-neighbour, long-haul, regional); `budget_estimator.py`'s stay/food tiers still unrecalibrated. Citation-backed public datasets researched as a systematic alternative to one-off screenshots (Kaggle India-domestic flight fares, a back-calculated Indian Railways ₹/km model, candidate worldwide flight/hotel datasets) — none yet applied; see `TECHNICAL_DOCUMENTATION.md` §14 v10.28 |
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
