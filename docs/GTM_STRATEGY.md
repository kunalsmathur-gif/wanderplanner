# WanderPlanner — GTM Strategy & Product Roadmap

**Date:** 2026-07-11
**Status:** Active plan
**Inputs:** [STARTUP_EVALUATION.md](STARTUP_EVALUATION.md) (+ 2026-07-11 addendum), first user interviews (July 2026), live market research (sources at end)
**Owner:** Solo founder, nights-and-weekends; plan is sized accordingly

---

## 1. Core thesis

The moat is **not** the chatbot, the voice UX, or any single feature — all replicable by a funded competitor in a sprint. The moat is three compounding assets:

1. **A proprietary, verified India-context corpus** — hidden-gem POIs scored from YouTube traveller-comment signal, verified against OSM; grounded India cost data (trains, veg meals, family math) no global player models. The comment corpus is complete across **170 destinations** as of v10.40.2. (Reddit was the original signal source; it was retired 2026-07-26 after blocking unauthenticated reads, and the multi-source diversification done beforehand is what kept this bet intact — see `docs/NEXT_SESSION_TODO.md`.)
2. **Measurable personalization fidelity** — published evals proving WanderPlanner itineraries respond to constraints ("I'm a Harry Potter fan", "less crowded beaches") when ChatGPT/Gemini output doesn't.
3. **Distribution in a channel funded players ignore** — India's offline travel agents.

User feedback (July 2026) was not "add features" — it was "make the intelligence real." The three complaints (touristy output, refinements don't bite, shallow budgets) share one root cause: generation is prompt-led, and the data that fixes it is built but unwired (`itinerary_corpus` is ingest-only as of this writing).

**Closing the feedback loop is now instrumented in-app (✅ built, issue #64).** The insights above originally came from direct interviews, not in-app instrumentation; there's now an in-app way for a user to flag "this itinerary missed the mark" or react to a specific day/place, tied to the exact request that produced it (`trip_config_snapshot`), plus admin-visible feedback volume and negative-feedback rate by destination. See `docs/PRD.md` Clarification #20, `docs/system-design.md` §9C. The agent/B2B side of feedback stays deliberately manual — hand-onboard a small number of real agents for free, talk to them directly, automate only once a few are willing to pay.

---

## 2. Product bets (mapped to user feedback)

### Bet 1 — Crowd-aware planning ("hidden gems")

Generic LLMs regurgitate top-10 lists — a structural weakness of every ChatGPT-wrapper competitor. The traveller-comment corpus contains the antidote: real people naming places that don't appear on any listicle. Mined from YouTube travel videos across **170 destinations** (complete as of v10.40.2), scored deterministically and verified against OSM.

- **Gem scoring:** rank POIs by high sentiment × low mention volume across the YouTube traveller-comment corpus (a beach praised in 4 mentions = gem signal; one appearing in 400 = crowd signal). Verify every candidate against OSM so a hallucinated place never ships. A composite authenticity weight (account/channel age, engagement corroboration, temporal-clustering and duplicate-text penalties) is planned to prevent low-volume-but-fake signal (e.g. paid reviews) from being mistaken for a genuine hidden gem — see `docs/NEXT_SESSION_TODO.md`.
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

> **Shipped today vs. this bet's paid-API vision:** the bullets above (Amadeus/Skyscanner/Booking/IRCTC) describe the target end-state once paid live-pricing APIs are wired in — not yet built. What's actually live today is a **free-tools, deterministic estimator** (`core/budget_estimator.py`) that already delivers the core "grounded, not guessed" positioning without any paid API: flights use real haversine distance between the user's two cities mapped to a fare band; stay/food first try a real median price mined from the app's own pre-scraped RAG corpus (Wikivoyage and YouTube-comment mentions for that exact destination) before falling back to a hand-authored, research-anchored flat table. The discipline that matters for the pitch: **if no real data is found for a destination, the code says so and falls back rather than letting the LLM invent a number** — the same "honest about what it doesn't know" positioning this bet is selling, already true pre-revenue. This is the free-tier proof point this bet's paid-API roadmap upgrades from, not a placeholder to be embarrassed about. Full mechanism explainer in `docs/PRD.md`'s R5 section and `docs/DEMO_DAY_FAQ_CHEATSHEET.md` Q14.

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

- **Best mode of contact: WhatsApp**, not a form-then-email flow — `wa.me/<agent_number>?text=<prefilled itinerary summary>` (destination, dates, pax, budget tier, shareable itinerary link). Matches where Indian users and offline agents already operate; a generic web form loses this audience. **Response commitment (now live):** the CTA persists the lead via `POST /api/agent-leads`, sends the traveler an immediate Resend confirmation email with an explicit 24-hour SLA, and then opens the WhatsApp deep link. **Separately, and new as of 2026-07-31: the agent side itself now gets notified immediately too** — a "New quotation request" email fires the moment the lead is created (not just on the 24h escalation path), carrying the trip inputs, the traveler's optional notes, an AI-itinerary summary, and the itinerary PDF as an attachment. Hourly SLA checks still escalate unanswered leads at 24h and reassure the user at 48h; an admin/agent must now explicitly click "Mark responded" in the admin console for a lead to count as answered — that's the only thing that stops the SLA clock. This is deliberately email-only infrastructure at this stage (no phone/OTP sign-in) — see `docs/PRD.md` Clarification #19 for why phone-based auth was evaluated and deferred, and Clarification #21 for the 2026-07-31 notification/notes/PDF/two-CTA update.
- **Traveler-supplied context, not just a bare CTA click:** the handoff card now also collects an optional, 100-word-capped free-text note ("anything specific to tell the specialist?") and attaches the generated itinerary PDF automatically — the agent opens a fully-briefed request, not a cold lead with just a destination name.
- **Who "the agent side" is, concretely:** every admin user, by default (sole-builder mode) — or, once a real agent/ops team exists, whoever is listed in `apps/api/config/agent_recipients.json`. Editing that file is the entire "onboard a new agent to receive leads" step; no code change or redeploy needed.
- **Implementation shape:** `apps/web/components/itinerary/AgentHandoffCard.tsx` + `POST /api/agent-leads` (`agent_leads` table) + a single concierge WhatsApp number for Phase 1. **Don't build automated matching before there's real agent supply** — automate only once the Phase 2 go-criterion (5 paying agents) is hit.
- **Incentive fit:** this is what makes an agent's ₹1,500–3,000/seat feel like more than "faster drafting software" — it's warm consumer demand bundled into (or later, monetized alongside) the subscription, a differentiator neither Sembark nor TravClan offers.
- **Metrics now on the admin dashboard** (issue #63): `agent_leads.created_total`, `responded_total`, `escalated_total`, `reassurance_sent_total`, `response_time_avg_hours`, `response_time_p50_hours`, `response_time_p90_hours`, `sla_breach_rate`, `marked_booked_total`, plus `top_destinations`. The admin lead queue now exposes two independent CTAs per lead — **"Mark responded"** (feeds the SLA/response-time numbers above) and **"Mark booked"** (revenue/conversion) — so "is it time to bring on a second person handling leads" is read off real response-time and SLA-breach numbers, not a vague sense of being busy.

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
| 2 | Hidden-gem scoring + crowd dial | Community signal × OSM verification | ✅ Done (v10.16, 2026-07-11) — BestTime live-crowd layer deferred (paid API). Source diversified to YouTube comments in v10.30.0, which is what let Reddit be retired in v10.40 without the bet regressing; Google Places/TripAdvisor remain on the roadmap — see `docs/NEXT_SESSION_TODO.md` |
| 3 | Refinement hard-constraints + visible diff UI | Interest→entity→verify→pin pipeline | ✅ Done (v10.17, 2026-07-12) — pins verified vs OSM/wiki, hard-pinned in the prompt, in-place regeneration + diff chips in Anya panel |
| 4 | Refinement-fidelity eval suite; publish vs-ChatGPT results | Builds on `docs/eval-set.csv` | ✅ Done (v10.20.0, 2026-07-14 → v10.23.0, 2026-07-15) — clean live run: fidelity **0.975**, recall 0.938, inclusion/stability **1.000**, honesty 4/4 (RF-010 recovered from the transient 503s; RF-012 improved to 0.67 untouched). Anti-distractor rule in `interest_expansion_chain.py` tuned to allow famous theatres/walk-of-fame monuments/celebrity residences as "specific" (was silently dropping true positives like Hollywood Walk of Fame, Prithvi Theatre); rerun 2026-07-15: fidelity **0.983** (+0.008), recall **0.958** (+0.020), inclusion/stability still **1.000**, honesty still 4/4 — **improvement confirmed, no regressions** (offline gate unaffected at 1.000, full backend suite green, 3-way manual re-probe validation before publishing). **Published** in `docs/eval-results/`: comparison piece + both dated verbatim report sets (2026-07-14 and 2026-07-15), with the Claude verbal-honesty disclosure, the recording protocol, and a "what we are NOT claiming" section. Founder to adapt for external channels |
| 5 | Turn on affiliate tracking on existing deep-links | Viator / GetYourGuide / Skyscanner | Pending — blocked on founder affiliate-program registrations. Link formats fixed in v10.20.0 (audit §1.2): Google Flights on supported `?q=` syntax, Skyscanner/MMT on IATA deep-links via static city-code map with honest search-page fallback — affiliate params can now be appended to working links |
| 6 | Eval infrastructure hardening: wizard-flow harness, LLM-as-judge quality metric, baseline/candidate compare + failure-clustering tools | Internal QA rigor underpinning the fidelity-eval trust claims above; see `docs/eval-set.md` §7 and `docs/system-design.md` §15A | ✅ Done (2026-07-18) — `eval/run_wizard_eval.py` closes the gap the fidelity suite didn't cover (multi-turn Anya wizard, not just refinement); `eval/judge_metrics.py` adds a subjective tone/personalization/coherence score alongside the existing deterministic accuracy/hallucination metrics in the model-comparison harness (the same harness that will produce future "vs ChatGPT/Claude" numbers); `eval/compare_results.py` + `eval/analyze_results.py` make baseline-vs-candidate regression checks and failure clustering routine instead of manual, so future published comparisons are backed by a repeatable, auditable process |
| 7 | Wire the golden-dataset **retrieval** eval (`eval/run_rag_eval.py`, distinct from the fidelity/wizard suites above) to the real `retrieve_context()` production path | It was scoring a simplified stand-in, not the code a real request runs; see `docs/rag-strategy.md` §16 and `docs/eval-set.md` §4U | ✅ Done (issue #50) — Recall@10 **0.95**, MRR **≈0.46**, nDCG@10 **≈0.58**, down from the old simplified-harness numbers (MRR ≈0.85–0.94). **Disclosed on purpose, not walked back:** production's 3-query RRF fusion (built for well-rounded itinerary days) naturally ranks single-topic queries lower than a harness that only ever tested one query at a time — a real, understood tradeoff, not a bug. Same standard of honesty as the 0/4-honesty-score disclosure in `docs/eval-results/` — this is the eval infrastructure catching its own prior blind spot, which is the point of having it |

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
- **Give Anya a voice of her own** (see below) — **traction-gated, not scheduled.**

#### Anya's own voice — long-term, gated on traction

**The intent.** Anya has a written personality today (`WIZARD_SYSTEM_PROMPT`: warm, Indian,
well-travelled, speaks Hindi or English to match the user) but **no voice of her own.** Voice mode
uses the Web Speech API, which means she is whatever voice the user's device happens to have
installed. A branded, consistent voice — via ElevenLabs or equivalent — is the natural completion
of the persona, and is a genuine differentiator for an India-first product where a warm Hindi voice
is a category of its own.

**Why it is deferred rather than built.** Today's voice costs nothing: no key, no per-request
spend, no added latency, works offline. Every one of those flips with a cloud TTS. That trade is
worth making for a product with users and worth nothing for one without, so this is explicitly
gated on traction.

**What it would actually fix** (the current state is measured, not assumed — see
`TECHNICAL_DOCUMENTATION.md` §14 v10.45.0):

- **Device fragmentation disappears.** A Hindi voice is absent on most Windows desktops and
  unguaranteed on macOS; on Android, Google's voices expose no name or gender, so we cannot even
  reliably pick a female one. A cloud voice is identical for every user on every device.
- **The persona becomes ownable.** "Anya sounds like Anya" is brand; "Anya sounds like Microsoft
  Heera, or Google's default, or nothing at all" is not.
- **Hindi speech stops being a device lottery** — the single biggest gap in the India-first story.

**What it costs, honestly.** Per-character billing on a path that currently runs free, on *every*
wizard turn; a network round trip added to a reply that is already the latency-sensitive part of
the product (streaming TTS mitigates but does not remove this); another production key to manage —
and this codebase has twice shipped a feature that silently no-opped in production because its key
was never set on Railway (`YOUTUBE_API_KEY`, `RESEND_API_KEY`). Any adoption needs a real
per-conversation cost estimate first, and a decision on whether voice becomes a paid-tier feature
rather than a default.

**Suggested gate:** revisit once Phase 2's go-criterion is met (5 paying agents) **or** consumer
voice-mode usage is measurably non-trivial — which is currently unknown, because nothing
instruments it. Cheapest first step is not the integration but the measurement: record voice-mode
activation rate before spending anything on it.

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
