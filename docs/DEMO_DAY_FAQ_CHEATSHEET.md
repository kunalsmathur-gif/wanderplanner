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
| `itinerary_corpus_extraction_chain.py` | Offline ingestion — turns scraped blogs/travel videos into few-shot corpus examples |

### Q3. How is orchestration/handover managed — central orchestrator, or simple handoff?

**Neither, in the agentic sense.** Orchestration is plain **deterministic backend code** (FastAPI routers in `apps/api/routers/`). A router receives a request, calls exactly one chain function, does deterministic pre/post-processing (RAG retrieval, safety filters, fallback tiers), and streams the result over SSE. Which chain runs is decided by **which screen/button the user is on** (user-navigation-driven), not by an LLM deciding to hand off to another agent.

### Q4. What context, knowledge base, and tools does each chain get?

- **Shared knowledge base:** Qdrant vector DB (cloud, free 1GB tier) — `wiki` (Wikivoyage), `osm_pois` (OpenStreetMap POIs), `youtube_comments` (traveller sentiment), `itinerary_corpus` (few-shot real itineraries), plus `itinerary_cache`. A legacy `reddit` collection still holds previously-ingested points and is still read at query time, but nothing writes to it any more (see Q7).
- **Retrieval:** hybrid semantic (sentence-transformers embeddings) + BM25 keyword search, RRF-merged, cross-encoder reranked (`ms-marco-MiniLM-L-6-v2`), HyDE query expansion — used mainly by `itinerary_chain.py`.
- **External tools/services:** OSM Overpass API (POI ingestion), Nominatim (geocoding), Wikivoyage scraper, YouTube Data API v3 (traveller comments), Pexels (hero photos), plus a 3-tier fallback (cache → RAG skeleton → enhanced mock) if the LLM call fails.
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
| ~~Reddit~~ | ~~Trip-report/hidden-gem corpus~~ | **Retired 2026-07-26 — no longer a source.** Reddit blocked unauthenticated reads, and its API now requires a written app review that never issued credentials. Rather than wait on an external approval with no ETA, that signal was moved to Wikivoyage + YouTube. See Q13. |
| YouTube Data API v3 | Hidden-gem sentiment (video comments) + itinerary-video discovery + narration/transcripts for price grounding | Free, and the one *metered* source. The cap that actually binds is **100 `search.list` calls per project per day** (its own meter — not the widely-quoted 10k units/day), resetting midnight Pacific, so both automatic callers sit behind a rolling-24h search budget |
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

An LLM only knows what it was trained on — ask it to plan a trip to a smaller Indian town and it will confidently invent plausible-sounding restaurants and "hidden gems" that don't exist (hallucination). RAG fixes this by handing the model **real, fresh source material** (Wikivoyage guides, traveller comments on YouTube travel videos, OpenStreetMap location data) before it writes anything — like giving an intern real research instead of asking them to imagine it.

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
- **Corpus density, not corpus size, is the live gap.** Reddit was retired as a source in v10.40 after it blocked unauthenticated reads and its API review never issued credentials. The honest framing if asked: **we measured what we'd actually lose before deciding, and it was less than assumed.** An earlier internal note called Reddit "the biggest unblocker" for price grounding; measuring money-shaped text per destination showed no corpus had real price density — YouTube comments carry only 1–3 price mentions per destination, so people simply don't quote prices in comments. The "hidden gems" signal now rests on YouTube comments (ingested automatically on a destination's first request, v10.38; corpus completed to 170/170 destinations in v10.40.2) plus Wikivoyage. **The real constraint is that a *complete* corpus is not a *dense* one** — food-cost grounding still returns "not grounded" for most destinations, and the fix is denser price-bearing text (Wikivoyage's priced listings, video transcripts where vloggers state costs aloud), not more tuning.
- **Retrieval can be the wrong tool for the question.** Found and fixed in v10.38: semantic search ranks by topical similarity, so it never surfaced casual price mentions ("Choki dani 700 per person") for cost-grounding queries — that comment is *about a restaurant*, not *about cost*. Presence of a price is a lexical property and is now tested lexically. A useful general caution: vector search answers "what is this text about", which is not always the question being asked.
- **Latency/throughput tradeoff.** Reranking (best quality) causes a ~3x throughput drop under load — so it's only turned on for the one call site (final itinerary generation) where it matters most.
- **Garbage-in-garbage-out.** RAG only grounds the model in what's in the database; if scraped content is wrong or spam, RAG will confidently retrieve and repeat it. It reduces hallucination — it doesn't guarantee truth.

Full detail in `docs/rag-strategy.md` (new section: "RAG Failure Modes & Where It Shines") and `docs/scaling-tech-challenges.md` §6a.

### Q14. When Anya recommends a budget, is that number real or is the LLM just making it up?

**Neither purely — it's a deterministic calculator with an honest fallback chain, not an LLM guess.** `core/budget_estimator.py` computes flights + stay + food as three separate numbers, each trying progressively "less specific" sources until one actually returns something, and the LLM is only asked to *present* the final number in its own words, never to invent it:
- **Flights:** real haversine distance between the user's two cities → a distance-banded fare range; falls back to one flat number per destination tier only if coordinates aren't available yet.
- **Stay/food:** first tries a real median price mined from the same Qdrant RAG corpus (Wikivoyage/YouTube-comment mentions, destination-filtered, regex-verified against a currency amount near an on-topic word like "per night"/"paid"/"cost" — not just any number in a nearby sentence); if that has too little signal (still the common case for most destinations today), it falls to a real Inside-Airbnb-derived rate for a small set of seeded cities, and only then to a hand-authored flat table (itself built from real anchor research, not invented).
- **Food specifically has one extra honesty rule (v10.38).** Most community price mentions are *per meal*, not per day, so turning them into a daily budget needs a meals-per-day assumption — and an assumption in the low direction would under-budget a user's trip, which is the harmful direction. So the estimator now distinguishes the two cases: when the corpus contains enough amounts already stated per *day* ("we spent ₹900 a day on food"), that figure is used directly with no assumption involved and trusted in both directions; when it only has per-meal prices, the converted figure is floored at the researched flat value so grounding can raise the estimate but never undercut it. In short: **we only let real data lower a number when the data is genuinely about that thing** — otherwise we keep the conservative figure and say so.
- **The key discipline:** if a step finds nothing, it returns "not grounded" and moves to the next fallback — it never lets the LLM fill the gap with a guess, which is exactly the failure mode this module exists to prevent. The user-facing answer always states which rung was used (e.g. "stay cost is grounded in real traveller-reported rates for this destination") so the estimate's honesty is never overstated.
- **Nothing is fetched live at request time** — all RAG content was scraped/embedded ahead of time and just gets searched, so a budget answer is instant and never depends on Wikivoyage/YouTube being up at that moment.

Full detail in `docs/PRD.md` (Epic/budget-estimator section) and `core/budget_estimator.py`'s module docstring.

---

## Part 5 — GTM: Consumer Hook & Monetization

### Q15. Once an itinerary is generated, what's the hook to get the user to contact an offline agency?

**A contextual CTA: "Get This Itinerary Booked by a Local Expert"** (not a cold "request a quotation" ask) — placed alongside the existing OTA booking-links section, right when trust in the plan is highest. Best contact mode is **WhatsApp**, not a form-then-email flow (`wa.me/<agent_number>?text=<prefilled itinerary summary>`), because that's where Indian users already are and where offline agents already work. This feeds real consumer demand into the paid "Anya for Agents" B2B product — the consumer app is the lead-gen engine; agents are the revenue engine. Implementation is a new `AgentHandoffCard.tsx` component + a `POST /api/agent-leads` endpoint + simple destination-based routing to onboarded agents (kept manual/simple in Phase 1 — don't automate matching before there's real agent supply). Full detail in `docs/GTM_STRATEGY.md`.

### Q16. Should the agency-facing product be white-labeled, or agency + WanderPlanner co-branded?

**Default to white-label, tiered by price** — not a permanent co-brand:
- The agency's *own* customer needs to trust the agency, not an unfamiliar SaaS brand riding along on their itinerary PDF — co-branding subtly signals "outsourced thinking" and risks planting the idea the traveller could cut the agency out next time.
- Precedent already validates this: mTrip, Sygic, Simplified.Travel are all proven white-label B2B models globally — nobody's done it India-native yet.
- **Tier 1 (base subscription, ~₹1,500/mo):** agency logo + brand colors on PDF/shareable link, small "Powered by WanderPlanner AI" footer tag only.
- **Tier 2 (premium seat, once 5-paying-agent go-criterion is hit):** true white-label — no attribution anywhere, optional custom subdomain — a natural upsell lever, standard SaaS "remove our branding" economics.
- Consumer-facing app itself stays 100% WanderPlanner-branded — white-labeling only applies to the B2B "Anya for Agents" surface and its outputs, so consumer brand equity isn't fragmented.

Full detail in `docs/GTM_STRATEGY.md` and `docs/MARKET_RESEARCH.md`.

---

## Part 6 — "What actually broke, and how did you catch it?" (Top 10 Gotchas)

**Why this section exists:** an honest build has bugs. What separates a serious product from a demo is whether they're found *before* users notice and whether the fix generalizes. All ten below shipped, were caught, root-caused, and fixed — with tests or a live re-verification behind each one. This spans the project's full history, not just one session. Full detail and exact version numbers are in `TECHNICAL_DOCUMENTATION.md` §14 if asked to go deeper on any single one.

### Q17. What's the single biggest thing that was quietly broken, and how was it found?

**RAG grounding returned nothing, in production, for weeks — with zero visible errors (v10.24.0).**
- **In plain terms:** every itinerary is supposed to be grounded in real scraped travel content (Wikivoyage guides, traveller comments, map data) before the AI writes anything. After we moved our vector database to its production cloud host, every single one of those lookups was silently rejected — the AI fell back to writing itineraries purely from its own general training knowledge, exactly the hallucination risk RAG exists to prevent, and nobody could tell from using the product because the fallback chain catches errors gracefully and just returns *a* plan.
- **Root cause:** the cloud version of our vector database refuses a filtered search (e.g. "only show me results for Rome") unless a special index exists on that field first. Our local testing environment doesn't enforce this rule, so it worked in every test we ran and broke only in the one place we weren't testing against — real production data.
- **The fix:** the app now creates that index automatically on every startup, and the existing 3-tier fallback (cached itinerary → real-data skeleton → templated) means a similar future outage degrades gracefully instead of silently.
- **How we found it:** while implementing an unrelated feature (on-demand ingestion), we ran a raw test query against the real production database for the first time and got an error where local testing had always returned success. In other words: this was found because we finally tested against the same system real users hit, not because anything alerted us.

### Q18. Was the AI ever recommending places that don't actually exist?

**Not hallucinated outright, but the safety net meant to prevent it was quietly broken for every single destination (v10.27.0).**
- **In plain terms:** we verify every AI-suggested landmark against real map data and travel-guide text before showing it to a user (the "Harry Potter test": ask for wizard-themed stops in London, and the system should only ever show real, verifiable places). We tested this live and found it had never actually worked — two separate bugs meant almost no verification signal existed for any destination.
- **Root cause 1:** our map-data scraper had a single result limit shared across all place categories, and in any city center, restaurants and cafes vastly outnumber landmarks — so the limit filled up entirely with food spots before a single museum or monument was ever fetched. London's already-collected map data was **100% restaurants and cafes, 0% landmarks.**
- **Root cause 2:** independently, our travel-guide scraper had silently returned **zero usable text for every destination, for every user, since it was built** — the travel-guide website had quietly changed its page layout months earlier in a way that made our scraper walk past all the real content without erroring.
- **The fix:** the map-data fetcher now pulls a much larger sample and round-robins fairly across categories instead of filling first-come-first-served; the guide scraper was patched to handle the new page layout with a fallback for the old one.
- **How we found it:** by literally trying the advertised feature end-to-end against live data instead of trusting that "it was built, so it works" — the same discipline this whole list is built on.

### Q19. Why would famous landmarks sometimes be missing from a city's recommendations entirely?

**They were structurally impossible to fetch, not just outranked (v10.40.0).**
- **In plain terms:** ask for a Kyoto itinerary and the AI might never mention Kiyomizu-dera or Kinkaku-ji — two of the most famous temples in Japan — no matter how good the ranking logic is, because they were never even in the pool of candidates to begin with.
- **Root cause:** our map-data query only asked for one specific data *shape* (a single point on the map). But truly famous sites — temple complexes, the Red Fort in Delhi, Jama Masjid — are mapped as *areas* (multiple connected points), not single points. It's like searching a phonebook for "restaurants" but only reading listings that start with the letter A — anything filed differently is invisible to the search, not merely low-ranked.
- **The fix:** added a second query that also asks for those area-shaped map features, restricted to ones carrying a "notability" tag (so it stays fast), and ranks by that notability so famous sites always win a slot over an ordinary café.
- **How we found it:** a live spot-check comparing what should obviously be in a city's pool (Google "top Kyoto temples") against what we'd actually fetched — the gap was too glaring to be a ranking issue.

### Q20. Have place names ever shown up in the wrong language, or "hidden gems" turned out to be something silly like a train station?

**Both happened, from two separate bugs (v10.39.0).**
- **In plain terms:** Tokyo's itinerary once showed 58 of 60 places by their Japanese-script name only (清水寺 instead of "Kiyomizu-dera") — unreadable to the traveller it was meant for. Separately, our "hidden gems" feature — which finds under-the-radar spots real travellers rave about online — was recommending things like Kadıköy metro station in Istanbul as a top find.
- **Root cause 1:** our map data pulls a place's name in whatever language the local map contributors used, with no fallback to an English name even when one exists in the same dataset.
- **Root cause 2:** the gem-scoring logic doesn't exclude transit infrastructure, so a train station mentioned constantly (because everyone passes through it) reads exactly like an enthusiastically-praised hidden find.
- **The fix:** name lookup now prefers the English name field, falls back to a Latin-script fragment inside the local name if that's all there is, and keeps the original name as a secondary field; gem scoring now explicitly excludes train stations, airports, and any place literally named after the destination itself.
- **How we found it:** an audit of every already-ingested destination for non-Latin-script names (17 of 170 were affected), and manually reading Istanbul's actual "hidden gems" output and noticing it was just transit stops.

### Q21. Has a simple wording bug ever caused something more serious, like removing family-friendly places or mispricing a destination?

**Five separate times, all the same root cause: matching a keyword as a raw substring instead of a whole word (v10.40.4–v10.40.6).**
- **In plain terms:** our kid-safety filter is supposed to strip adult-oriented venues (bars, pubs) from family itineraries. Because it checked whether the word "pub" appeared *anywhere* inside a place's name, it also matched and deleted **"Public Garden"** and **"Public Library"** — genuinely kid-friendly places, silently removed with no error shown. The same style of bug separately made "Sukhothai" (a moderate-budget Thai destination) get priced as a premium destination, because the budget-tier code matched the two-letter code "uk" anywhere inside the name.
- **Root cause:** several independent modules each used a plain "is this text contained in that text" check instead of "does this exact word appear," which quietly misfires on longer words that happen to contain a shorter flagged word.
- **The fix:** all keyword matching in the codebase now goes through one shared, word-boundary-aware matching function, so the fix applies everywhere at once, not module-by-module.
- **How we found it:** the first instance (food-related pricing) was found while investigating something unrelated; that success prompted a deliberate sweep of every similar keyword-matching call site in the codebase, which turned up four more.

### Q22. Since WanderPlanner is India-first, has content in Hindi ever been accidentally ignored?

**Yes, two compounding bugs meant Hindi-language travel-vlog content was functionally invisible for cost estimates (v10.41.0).**
- **In plain terms:** we pull real cost information from what travel vloggers say out loud in their videos. For Indian destinations, most vloggers speak Hindi — but the system was only requesting English captions, so it silently discarded the Hindi track entirely, even when it was the only one available.
- **Root cause 1:** the caption-fetching code only ever asked for the English-language track.
- **Root cause 2:** even after fixing that, a lower-level text-matching rule (checking for a "whole word," not a substring — see Q21) is defined in a way that simply doesn't work correctly for Hindi script: a rule meant to say "match the whole word, not part of one" happens to fail specifically on Hindi words that end in certain vowel marks, so **zero of 24 genuinely price-bearing Hindi sentences** were recognized as being about food or lodging at all, even once fetched.
- **The fix:** caption fetching now requests English **and** Hindi; the word-matching rule was rewritten to correctly recognize Hindi script characters as "part of a word," not just Latin letters.
- **How we found it:** live-testing a Jaipur destination and noticing the fetched caption text mentioned costs but the system still reported "no price data found" — the number of matched chunks should have gone up, and it hadn't.

### Q23. Has the system ever built an itinerary for entirely the wrong city?

**Yes — three same-named cities were silently swapped for the wrong one, and it wasn't caught by our main quality check (v10.37.0).**
- **In plain terms:** asking for "Austin" returned data for a ~150-person former mining town in Nevada, not Austin, Texas. "La Paz" returned Mexico's La Paz, not Bolivia's capital. "Valencia" returned a city in Venezuela instead of Spain. All three looked completely fine to our automatic data-quality check, which only counts *how much* data a destination has, never *whether it's the right city*.
- **Root cause:** our free geocoding service picks a "best guess" match for an ambiguous place name, and for these three, its best guess was a different, real place that happens to share the exact name.
- **The fix:** added a manual override list forcing these specific, known-ambiguous names to the correct city, plus new tests locking that behavior in; also wiped and re-fetched the wrong-city data so it couldn't silently persist.
- **How we found it:** manually spot-checking destinations that had *passed* our automatic quality check, cross-referencing the country each one geocoded to against where we expected it to be — a check specifically designed to catch what the automatic count-only gate structurally cannot.

### Q24. Has a "successful-looking" retry ever actually been quietly failing forever?

**Yes — a retry-tracking bug meant one destination would have retried an unfixable failure indefinitely, never marked done (v10.41.1).**
- **In plain terms:** our re-ranking pipeline is supposed to give up gracefully — and keep whatever good data it already had — after 3 failed attempts, so a single stubborn destination can't stall a batch job forever. One specific failure mode (the external map-data service refusing every request, on every attempt) skipped that safety net entirely and would have retried the same destination on every future run, forever, never reporting success even though nothing was actually going wrong with its stored data.
- **Root cause:** the "give up after 3 tries" logic only fires if the attempt reports *some* data was fetched. But when the external service fails completely (rather than returning thin or low-quality data), the code returned "0 fetched" instead of "kept what was already there" — which looks identical to a real failure to the bookkeeping logic, so the 3-strikes rule never got to fire.
- **The fix:** that code path now reports the existing preserved data instead of zero, matching how two very similar, already-existing safety checks in the same function behave.
- **How we found it:** while finishing a routine data-refresh job, one specific destination (Medellin) kept coming back as "still pending" run after run with an identical error — a pattern real bugs make and random bad luck doesn't.

### Q25. Has a security-relevant setting ever been silently inactive in production without anyone noticing?

**Yes — two production safety checks (a strict cookie-security rule and a secret-key strength check) were silently never running at all, for the app's entire time in production (v10.38.2).**
- **In plain terms:** the checks were written correctly and passed every local test — but they only activate by reading one specific "are we in production?" signal, and our production hosting platform never actually sets that exact signal; it sets two related ones instead. The checks always concluded "we must not be in production" and skipped themselves.
- **Root cause:** the code checked for one environment variable name; the hosting platform uses different ones.
- **The fix:** the "are we in production?" check now recognizes all three variable names hosting platforms commonly use.
- **How we found it:** a deliberate audit of every environment-dependent guard in the codebase against what the actual hosting platform sets — not triggered by an incident, a precaution that happened to catch a real gap before it caused one.

### Q26. Bottom line — what's the pattern across all ten?

Every single one of these was **invisible to the user in the moment** — no error message, no crash, just quietly worse or wrong output — and every single one was caught by the same discipline: **testing against real production data/services instead of trusting that local tests passing means it works, and periodically auditing "does the passing case actually look right", not just "did the check pass."** That's also why an eval harness and this kind of retrospective sweep are treated as core engineering work here, not overhead.

---

*Maintainer: Founder/PM · Last updated: 2026-07-27 · Companion to `docs/system-design.md`, `docs/rag-strategy.md`, `docs/scaling-tech-challenges.md`, `docs/GTM_STRATEGY.md`, `docs/MARKET_RESEARCH.md`.*
