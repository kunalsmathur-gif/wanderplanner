# WanderPlanner — Demo Day FAQ Cheatsheet

**Audience:** Non-technical PM/founder presenting a live demo, fielding audience Q&A.
**Purpose:** Fast, accurate, confident answers — in the sequence they're most likely to come up (architecture basics → depth/rigor → scaling/roadmap → GTM/monetization). Every answer is grounded in what's actually built, with exact file paths so any follow-up ("show me") can be answered on the spot.

**Related deep-dive docs:** `docs/system-design.md`, `TECHNICAL_DOCUMENTATION.md`, `docs/rag-strategy.md`, `docs/scaling-tech-challenges.md`, `docs/GTM_STRATEGY.md`, `docs/MARKET_RESEARCH.md`, `docs/pitch-deck/index.html`.

---

## Part 1 — Architecture Basics ("Is this really AI, or a wrapper?")

### Q1. Is WanderPlanner a single agent or multi-agent system?

**Single-agent, multi-chain.** One LLM (Google Gemini) is called through **8 distinct, independently-prompted "chains"** — Python functions, each with its own system prompt and temperature, invoked by deterministic backend code. There's no autonomous agent framework (no AutoGen/CrewAI), no agent-to-agent negotiation or handoff protocol. Think "one brain, several scripted personas/tasks," not agents talking to each other.

### Q2. What are the responsibilities of each chain?

| Chain (file, in `apps/api/chains/`) | Job |
|---|---|
| `wizard_chat_chain.py` | "Anya" conversational wizard — extracts 6 required trip fields from chat/voice |
| `chat_refine_chain.py` | Post-generation chat — patches itinerary config, answers questions |
| `interest_expansion_chain.py` | Expands a named interest (e.g. "Harry Potter") into verifiable places |
| `itinerary_chain.py` | Generates the actual day-by-day itinerary (the core product) |
| `extract_trip_chain.py` | Extracts trip intent from a pasted URL/blog/Reddit text |
| `recommend_cities_chain.py` | Suggests destination cities |
| `feasibility_chain.py` | Checks trip feasibility (time/budget/logistics) |
| `itinerary_corpus_extraction_chain.py` | Offline ingestion — turns scraped blogs/Reddit into few-shot corpus examples |

### Q3. How is orchestration/handover managed — central orchestrator, or simple handoff?

**Neither, in the agentic sense.** Orchestration is plain **deterministic backend code** (FastAPI routers in `apps/api/routers/`). A router receives a request, calls exactly one chain function, does deterministic pre/post-processing (RAG retrieval, safety filters, fallback tiers), and streams the result over SSE. Which chain runs is decided by **which screen/button the user is on** (user-navigation-driven), not by an LLM deciding to hand off to another agent.

### Q4. What context, knowledge base, and tools does each chain get?

- **Shared knowledge base:** Qdrant vector DB (cloud, free 1GB tier) — 4 collections: `wiki` (Wikivoyage), `reddit` (trip reports/tips), `osm_pois` (OpenStreetMap POIs), `itinerary_corpus` (few-shot real itineraries), plus `itinerary_cache`.
- **Retrieval:** hybrid semantic (sentence-transformers embeddings) + BM25 keyword search, RRF-merged, cross-encoder reranked (`ms-marco-MiniLM-L-6-v2`), HyDE query expansion — used mainly by `itinerary_chain.py`.
- **External tools/services:** OSM Overpass API (POI ingestion), Nominatim (geocoding), Reddit public JSON feed (currently blocked, 403 in prod), Wikivoyage scraper, Pexels (hero photos), plus a 3-tier fallback (cache → RAG skeleton → enhanced mock) if the LLM call fails.
- Each chain only gets the context relevant to its own job — e.g. the itinerary chain gets RAG context + trip config; the extract-trip chain only gets the raw pasted text.

### Q5. Does each agent/chain have its own system prompt — where exactly?

Yes — hardcoded directly inside each chain's Python file (not externalized to a prompt-config file):
- `apps/api/chains/wizard_chat_chain.py` — "Anya Wizard" (v5)
- `apps/api/chains/chat_refine_chain.py` — "Anya Post-Gen Chat"
- `apps/api/chains/itinerary_chain.py` — "Itinerary Generation"
- `apps/api/chains/extract_trip_chain.py` — "Extract Trip"
- Full verbatim prompt text is also mirrored in `docs/system-design.md`, section **"10. Gemini Prompt Design & Temperature Settings."**

### Q6. What are the LLMs used, per chain?

All chains run on **Google Gemini** (`gemini-2.5-flash` default). Itinerary generation has a scripted fallback chain on rate-limit/503 errors: `gemini-2.5-flash` → `gemini-2.5-flash-lite` → `gemini-1.5-flash`. Groq (Llama 3.1/3.3-70B) exists as a configurable alternate provider but isn't the production default. The eval "judge" scoring other models is deliberately pinned to a **fixed** `gemini-2.5-flash` to avoid self-grading bias. No per-chain model specialization — differentiation is via **prompt + temperature** only (0.1 extraction, 0.4 itinerary/wizard, 0.5 chat-refine).

### Q7. What APIs does every chain/agent call — name, purpose, cost?

| API | Purpose | Cost |
|---|---|---|
| Google Gemini (2.5-flash / flash-lite / 1.5-flash) | All LLM chains | Paid, pay-per-token |
| Groq (Llama 3.1/3.3-70B) | Alternate LLM provider (config-switchable) | Paid, currently unused fallback |
| Qdrant Cloud | Vector search / RAG knowledge base | Free tier (1GB) |
| OSM Overpass API | POI ingestion | Free (public) |
| Nominatim (OpenStreetMap) | Geocoding | Free (public, ToS rate-limited) |
| Reddit public JSON feed | Trip-report/hidden-gem corpus | Free, currently 403 in prod (blocked, approval pending) |
| Wikivoyage | Destination guide text | Free (scraper) |
| Pexels | Hero/day photos | Free tier |
| BestTime.app / Google Popular Times (planned) | Live crowd forecasts | Not yet wired |

---

## Part 2 — Rigor: Evaluation, Testing, Proof

### Q8. What are the evaluation criteria per chain, and where do results live?

All in `apps/api/eval/`:
- **Datasets:** `golden_dataset.json` (RAG retrieval), `model_comparison_dataset.json`, `red_team_dataset.json` (prompt-injection/jailbreak), `refinement_fidelity_dataset.json`, `wizard_dataset.json`.
- **Config/thresholds:** `apps/api/eval/eval_config.json` — accuracy 0.7, hallucination 0.2, judge 0.6 thresholds; judge model fixed to `gemini-2.5-flash`.
- **Runners:** `run_model_comparison.py`, `run_red_team_eval.py`, `run_refinement_eval.py`, `run_wizard_eval.py`, `run_rag_eval.py`.
- **Criteria:** accuracy, hallucination rate, cost, latency, LLM-as-judge quality (tone/personalization/coherence) for itineraries; attack-success-rate/robustness for red-team; field-leak/chip-alignment checks for the wizard.
- **Results stored in:** `apps/api/eval/out/` (e.g. `model_comparison_results.json`, `wizard_eval_results_20260718_171437.json`) and human-readable competitive write-ups in `docs/eval-results/` (`report_vs_chatgpt_2026-07-15.md`, `report_vs_claude_sonnet_2026-07-15.md`).
- **Baselines:** `apps/api/eval/baselines/chatgpt_refinement.json`, `claude_sonnet_refinement.json`.

---

## Part 3 — "Why not build it bigger?" (Multi-agent, at scale)

### Q9. Given current scope/GTM/scaling plans, does a multi-agent system make more sense than single-agent?

**No — single-agent (multi-chain) has more merit today.** Reasoning:
- **The moat isn't orchestration.** Per `docs/GTM_STRATEGY.md`, the moat is the verified India corpus + measurable personalization fidelity + offline-agent distribution — none of that needs agents negotiating with each other.
- **Latency budget is tight.** `docs/PRD.md` mandates a 15–20s generation window; multi-agent patterns (planner→critic→executor loops) multiply LLM round-trips — the opposite of what's needed.
- **Cost.** Solo-founder, pre-revenue, pay-per-token. Extra agent hops = extra billed calls for marginal benefit already captured cheaply via prompt/temperature specialization.
- **Team size / operability.** Multi-agent systems are harder to debug and eval (compounding failure modes); the eval maturity to safely run that isn't there yet — and the *current simple* architecture is what caught a real production bug (RAG silently failing for months).
- **Determinism where it matters.** Safety filters, kid-content stripping, persona injection, fallback tiers are deterministic Python today — more debuggable/testable than delegating to an LLM "agent."

**Where multi-agent *would* start to make sense later (not now):** autonomous multi-step booking/negotiation across live APIs with re-planning; a dedicated "verifier" agent (though this is already handled more cheaply via deterministic OSM/wiki verification code); per-market specialization at scale (e.g., genuinely divergent behavior per region, not just prompt swaps). Full reasoning recorded in `docs/system-design.md` §1A and `docs/scaling-tech-challenges.md` §9.

---

## Part 4 — RAG (Retrieval-Augmented Generation)

### Q10. Why do we use RAG — in plain English?

An LLM only knows what it was trained on — ask it to plan a trip to a smaller Indian town and it will confidently invent plausible-sounding restaurants and "hidden gems" that don't exist (hallucination). RAG fixes this by handing the model **real, fresh source material** (scraped Reddit posts, Wikivoyage guides, OpenStreetMap location data) before it writes anything — like giving an intern real research instead of asking them to imagine it.

### Q11. How do we actually use it?

1. On each itinerary request, we search our own Qdrant vector database for the destination — three query variants in parallel (general highlights, vibe/hidden-gems/pace, practical food/transport/safety).
2. Results are merged (Reciprocal Rank Fusion of semantic + BM25 keyword search) and reranked with a cross-encoder for precision.
3. Compressed to a ~600-token "briefing note" and injected into the itinerary prompt alongside the trip request.
4. If the LLM or retrieval fails outright, a 3-tier fallback kicks in: cached similar itinerary → OSM-data-only skeleton → lightly templated itinerary with real tip snippets spliced in — so users essentially never see a hard error.

### Q12. How do we evaluate RAG performance?

A hand-labeled "golden dataset" (`apps/api/eval/golden_dataset.json`) with known correct retrievals, scored with standard IR metrics via `apps/api/eval/run_rag_eval.py`: **Precision@10**, **Recall@10**, **MRR**, **nDCG@10**. This objective harness is exactly what caught a real production bug — RAG silently returning nothing for months due to a missing Qdrant payload index.

### Q13. Where does RAG shine, and where will it start failing?

**Shines:**
- Grounding itinerary generation in real, verifiable local content instead of parametric-memory guesses.
- Multi-tier fallback keeps the product usable even when the LLM or retrieval fails.
- Objective, repeatable IR-metric evals catch regressions before users do.

**Fails / breaks down:**
- **Thin coverage.** Curated corpus covers ~134 destinations; only 11 are India-specific despite India being the core user base. Ask about a smaller town outside that list → little-to-no real data → silent fallback to the LLM's own general knowledge (i.e., hallucination risk returns).
- **Storage ceiling.** Free 1GB Qdrant cluster fits the current corpus many times over but is explicitly not sized for eager global expansion.
- **Freshness decay.** 18-month half-life time-decay scoring means stale, unrefreshed destination content is gradually deprioritized and eventually filtered out.
- **Broken ingestion pipelines.** Reddit ingestion is 403'd in production right now (real, live gap, not hypothetical) — the "hidden gems" signal is currently starved for many destinations.
- **Latency/throughput tradeoff.** Reranking (best quality) causes a ~3x throughput drop under load — so it's only turned on for the one call site (final itinerary generation) where it matters most.
- **Garbage-in-garbage-out.** RAG only grounds the model in what's in the database; if scraped content is wrong or spam, RAG will confidently retrieve and repeat it. It reduces hallucination — it doesn't guarantee truth.

Full detail in `docs/rag-strategy.md` (new section: "RAG Failure Modes & Where It Shines") and `docs/scaling-tech-challenges.md` §6a.

---

## Part 5 — GTM: Consumer Hook & Monetization

### Q14. Once an itinerary is generated, what's the hook to get the user to contact an offline agency?

**A contextual CTA: "Get This Itinerary Booked by a Local Expert"** (not a cold "request a quotation" ask) — placed alongside the existing OTA booking-links section, right when trust in the plan is highest. Best contact mode is **WhatsApp**, not a form-then-email flow (`wa.me/<agent_number>?text=<prefilled itinerary summary>`), because that's where Indian users already are and where offline agents already work. This feeds real consumer demand into the paid "Anya for Agents" B2B product — the consumer app is the lead-gen engine; agents are the revenue engine. Implementation is a new `AgentHandoffCard.tsx` component + a `POST /api/agent-leads` endpoint + simple destination-based routing to onboarded agents (kept manual/simple in Phase 1 — don't automate matching before there's real agent supply). Full detail in `docs/GTM_STRATEGY.md`.

### Q15. Should the agency-facing product be white-labeled, or agency + WanderPlanner co-branded?

**Default to white-label, tiered by price** — not a permanent co-brand:
- The agency's *own* customer needs to trust the agency, not an unfamiliar SaaS brand riding along on their itinerary PDF — co-branding subtly signals "outsourced thinking" and risks planting the idea the traveller could cut the agency out next time.
- Precedent already validates this: mTrip, Sygic, Simplified.Travel are all proven white-label B2B models globally — nobody's done it India-native yet.
- **Tier 1 (base subscription, ~₹1,500/mo):** agency logo + brand colors on PDF/shareable link, small "Powered by WanderPlanner AI" footer tag only.
- **Tier 2 (premium seat, once 5-paying-agent go-criterion is hit):** true white-label — no attribution anywhere, optional custom subdomain — a natural upsell lever, standard SaaS "remove our branding" economics.
- Consumer-facing app itself stays 100% WanderPlanner-branded — white-labeling only applies to the B2B "Anya for Agents" surface and its outputs, so consumer brand equity isn't fragmented.

Full detail in `docs/GTM_STRATEGY.md` and `docs/MARKET_RESEARCH.md`.

---

*Maintainer: Founder/PM · Last updated: 2026-07-19 · Companion to `docs/system-design.md`, `docs/rag-strategy.md`, `docs/scaling-tech-challenges.md`, `docs/GTM_STRATEGY.md`, `docs/MARKET_RESEARCH.md`.*
