# Next-Session TODO — Post-Cloud-migration cleanup → Reddit approval → Phase 2

**Last updated:** 2026-07-20 (budget estimator distance/RAG-grounding overhaul + production cross-origin auth cookie fix; see "This session" section immediately below, and v10.26.0 in `TECHNICAL_DOCUMENTATION.md` §14 for full detail)
**Context:** A routine dependency-bump task (`google-genai` 1.2.0→2.10.0, dependabot PR #8) led to discovering that Qdrant Cloud has been silently rejecting every `destination`-filtered RAG query since the Cloud migration (2026-07-15) — meaning real research context has likely not been reaching the live LLM prompt at all, degrading itinerary quality invisibly (the failure was swallowed by the fallback chain, never surfaced as an error). **This is fixed in code but needs a Railway redeploy/restart to actually take effect in production** — see "Do this first" below. The user is targeting a POC round of real testers soon; items 1-3 in the "Remaining items" list below are what came out of a 2026-07-16 discussion about what's actually needed before that.

---

## 🆕 This session (2026-07-20) — Budget estimator overhaul + production auth fix

Two live-user-reported bug investigations, both root-caused and fixed. Full detail in `TECHNICAL_DOCUMENTATION.md` §14 v10.26.0.

**Budget estimator:**
- ✅ Flight cost now requires departure city (previously never asked) and uses a real haversine-distance band (`core/distance_pricing.py`) instead of one flat number per destination tier — recalibrated against a real ₹27,000 Bengaluru→Colombo fare the user found.
- ✅ Stay/food now attempt real per-destination community-reported data via the existing free RAG collections (`core/price_extraction.py` + `core/cost_grounding.py`, deterministic regex extraction, no LLM call) before falling back to the flat table.
- ✅ Food's flat fallback recalibrated ~2-2.5x upward per real research (was undershooting real mid-range dining costs); stay's flat fallback checked against research and left unchanged (was already close).
- ✅ 27 new tests; full backend suite green (258 passed, 6 skipped).

**Production auth loop (signed-in users asked to sign in again; signup then "already have an account"; sign-in appeared to loop):**
- ✅ Root cause: `COOKIE_SAMESITE=lax` on a cross-origin (Vercel + Railway) deployment silently drops session cookies on every credentialed request. Fixed by setting `COOKIE_SAMESITE=none` in Railway's env — **confirmed working in production.**
- ✅ Added a `core/config.py` startup validator so this can't silently regress again (refuses to boot in production with the wrong value).
- ✅ Added the missing token-refresh-on-401 flow client-side (`lib/authApi.ts::refreshSession()`, wired into `authStore.hydrate()` and `api.ts::streamItinerary()`) — a second, independent bug (15-min access token, working backend `/auth/refresh` endpoint, nothing on the frontend ever called it).

**Not done yet — carry forward (see new items 9-11 below):**
- The RAG-grounding path for stay/food is real but currently a no-op everywhere — verified live against the real Qdrant Cloud cluster that `wiki`/`reddit` collections have 0 points. Re-verify it actually fires once Reddit/Wikivoyage ingestion is unblocked (item 4 below).
- Only the "budget" destination-tier / mid_range flight+food figures have a real research anchor. The other distance bands (regional/long-haul/ultra-long-haul) and destination tiers (moderate/premium) were extrapolated, not independently verified — recalibrate the same way (find a real fare/cost data point, anchor to it) as more come up.
- Found (not caused) a **pre-existing stale test**: `tests/integration/test_auth.py::test_signup_rejects_duplicate_email` expects a generic error message; the actual code intentionally returns a more specific one per an existing product-decision comment in `routers/auth.py`. Needs either the test or the comment/behavior reconciled — wasn't in scope to fix this session.

---

## 🆕 2026-07-18 — Eval infrastructure hardening

Reviewed the existing eval harnesses against the standard "Quality Flywheel" methodology (dataset → inference → grading → failure analysis → optimize) and closed all 6 gaps found:

- ✅ `eval/run_wizard_eval.py` + `wizard_dataset.json` + `wizard_checks.py` — first automated coverage of the Anya wizard multi-turn flow; live-verified 10/10 turns passing, regression-checks the exact 2026-07-18 budget/pace chip-mismatch bug (`wizard_chat_chain.py` fix).
- ✅ `eval/judge_metrics.py` — LLM-as-judge tone/personalization/coherence scoring wired into `run_model_comparison.py`, judge fixed independent of model-under-test.
- ✅ `eval/compare_results.py` + `eval/analyze_results.py` — baseline-vs-candidate diff and failure clustering, tested against real wizard output and synthetic red-team/model-comparison data. Both harness runners now write timestamped output.
- ✅ `eval/eval_config.json` + `config_loader.py` — externalizes wizard checks-to-run, judge model/toggle, default run params, and analyze thresholds.
- ✅ Docs: `docs/eval-set.md` §7 (process discipline), `docs/PRD.md` §10 (types of evals), `docs/system-design.md` §15A, `TECHNICAL_DOCUMENTATION.md` §8A, plus pointers in `docs/itinerary-generation-flow.md` and `docs/GTM_STRATEGY.md`.

**Not done yet — carry forward:**
- **Actually run `run_model_comparison.py`/`run_red_team_eval.py` live with the new judge metric enabled**, across real candidate models (still cost-gated, deliberately not run this session beyond the tooling's own synthetic/live-wizard verification — see item 0 below, now updated to reflect the judge/compare/analyze additions).
- **No unit tests yet for the new eval tooling itself** (`compare_results.py`, `analyze_results.py`, `config_loader.py`, `judge_metrics.py`) — only ad hoc manual verification (synthetic fixtures + one live wizard run) was done this session. Worth a `tests/unit/test_eval_tooling.py` pass if these become load-bearing for CI gating later.
- **`eval_config.json`'s `metrics_to_run` lists are currently descriptive, not yet enforced** — `run_rag_eval.py`/`run_red_team_eval.py`'s scoring functions don't actually branch on them yet (only `wizard.checks_to_run` is wired to gate real behavior). Low priority unless a specific metric needs to be toggled off in practice.

---

## 🔴 Do this first — verify the production fix actually landed

1. **Confirm Railway has redeployed/restarted since this session's `core/qdrant.py` fix shipped.** The payload-index creation only runs once per process start (`_ensure_collections()`, called from `get_qdrant()` on first use). If Railway's process wasn't restarted after this commit, prod is still silently 400-ing on every filtered RAG query. Check via Railway dashboard deploy history, or logs for a fresh `_ensure_collections` run.
2. **Verify from Railway logs**: filter for `destination` or `Index required` — should see zero occurrences after the redeploy. If you still see 400s, the index creation itself needs debugging against the prod cluster (should be identical to what worked locally, but confirm the prod `QDRANT_URL`/`QDRANT_API_KEY` point at the same cluster used to verify this fix).
3. **Once confirmed live**, consider re-running (or waiting for) a few real itinerary generations and spot-checking whether the RAG context block actually contains real retrieved content now (vs. the "No pre-fetched research available" sentinel it would silently fall back to before).

## ⏭️ Remaining items (in suggested order — items 1-3 are POC-readiness priorities per 2026-07-16 discussion)

### 0. Run the new LLM model-selection + red-team evals live (harnesses now include a judge metric + compare/analyze tooling, built 2026-07-16 → hardened 2026-07-18, still not run live end-to-end)

In response to a "should we use MMLU/GPQA to pick the LLM?" discussion, two eval harnesses were built 2026-07-16 but **deliberately not run** (live API calls cost real money): `apps/api/eval/run_model_comparison.py` (accuracy/hallucination/latency/cost — and, as of 2026-07-18, LLM-as-judge tone/personalization/coherence — across candidate models on the real production itinerary prompt, see `docs/eval-set.md` §8) and `apps/api/eval/run_red_team_eval.py` (injection/exfiltration/kids-safety-bypass/cost-abuse robustness per model — §9). Both were import/smoke-tested against synthetic data only; the 2026-07-18 session additionally live-verified the new wizard harness and the judge metric individually, but did **not** run a full multi-model sweep with either harness.

To actually run them next session:
- Add `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` to `.env` for whichever of OpenAI/Anthropic should be in the comparison (Gemini + Groq already have keys configured).
- `pip install -r requirements-ml.txt` (adds the new optional `groq`/`openai`/`anthropic` SDKs).
- Run both: `python -m eval.run_model_comparison --models <ids>` and `python -m eval.run_red_team_eval --models <ids>` from `apps/api` (each prints a cost estimate and asks to confirm — pass `--yes` to skip).
- Review the timestamped `eval/out/model_comparison_report_<ts>.md` and `eval/out/red_team_report_<ts>.md` (or the `_latest`-aliased fixed filenames), decide whether to switch `gemini_model`/`llm_provider` based on the results — the judge's tone/personalization/coherence sub-scores now sit alongside the deterministic accuracy/hallucination numbers, so a cheaper model that's structurally "accurate" but reads generically won't look artificially good.
- Once a second run exists, try `python eval/compare_results.py <first-run>.json <second-run>.json` and `python eval/analyze_results.py <run>.json` — this session verified both tools against real wizard-eval output and synthetic red-team/model-comparison fixtures, but neither has been exercised against a real multi-model run yet.
- Related gap surfaced while building this: **no unit test exists for `core/prompt_guard.py`** (the regex-level injection-neutralization logic) — worth a quick `tests/unit/test_prompt_guard.py` alongside or before the red-team run.

### 1. Security checks before any real (even POC) traffic

Not reviewed this session — needs a fresh pass before opening the app to real testers, even a small POC group. `docs/scaling-tech-challenges.md`'s risk-tiering table has a "Now (any traffic)" bucket that should be re-verified against current code, not assumed still valid: SSRF protection on `extract-trip`'s URL-fetching path, rate limiting on LLM-calling endpoints, sanitized error responses (no raw provider stack traces reaching the client — `core/errors.py::sanitize_error()` exists, confirm it's applied everywhere it should be), pinned dependencies + dependency/secret scanning in CI, structured logging/basic observability (Sentry/APM) so a POC session's failures are actually visible. Also worth a quick check that no secrets leaked into git history from this session's `.env` edits (they shouldn't have — `.env` is gitignored and nothing in the diff touched it — but worth a `git log -p -- apps/api/.env` sanity check).

### 2. Refresh OSM POI data for big cities before POC (elevated priority — was "low priority," now tied to POC quality)

Paris, Mumbai, Delhi, Bangkok, New York, and ~28 others are still missing real OSM data (persistently Overpass-rate-limited even at 12s delay across two retry passes — see `apps/api/scripts/retry_osm_ingest_pass2.py`'s `STILL_ZERO` list in git history for the exact set). These are exactly the destinations POC testers are statistically most likely to try, and without real POI grounding those itineraries lean more on the LLM's own knowledge (still generates fine, just a weaker showcase of the "verified real places" value prop). Needs actual exponential backoff / longer delays (30s+, possibly a dedicated slower job run over a longer window) rather than more retries at the same 12s cadence, which already hit diminishing returns.

### 3. Hidden gems — alternative data source if Reddit approval doesn't come through in time

Reddit's approval has no ETA (see item 4 below), so the "hidden gems" feature (`services/gems.py`) currently has zero real sentiment data to work with — it degrades gracefully (empty result) but isn't demo-able for a POC. **2026-07-16 follow-up session did the full research pass** (below) — this is no longer "candidate directions to evaluate," it's a scoped plan ready to build, gated only on the doc-commit step described at the end of this item.

**✅ Build now (free, reuses existing infra):**
- **YouTube transcripts** — extend the already-wired but empty `YOUTUBE_ITINERARY_VIDEO_IDS` list in `scrapers/itinerary_corpus.py` via live YouTube Data API v3 `search.list` calls per destination (100 units/query, free 10k-units/day quota) instead of manual curation.
- **YouTube comments** (new) — `scrapers/youtube_comments.py`: `commentThreads.list` (1 unit/call, free) per discovered video, chunked like Reddit posts, into a new `youtube_comments` Qdrant collection. Comments are structurally identical to Reddit posts (place mention + sentiment, real volume) — reuses `gems.py`'s lexicon/mention-counting logic almost unchanged. Needs a new free `YOUTUBE_API_KEY` env var.
- **Generalize `services/gems.py`** to blend `reddit` + `youtube_comments` mentions with per-source provenance, instead of the current hardcoded single-collection scroll. Ships working today off YouTube alone since Reddit is down in prod; Reddit signal layers back in for free whenever/if approval lands.
- **Expand `scrape_all_travel_blogs()`'s RSS feed list** with 2-3 more blogs, ideally "hidden gems"-angled — zero new code.

**🕒 Roadmap — paid or needs a quick pricing/legal pass, not free/immediate:**
- **Google Places API** (`rating` + `userRatingCount` as a structured gem signal — low count + high rating = gem, no lexicon guesswork). Estimated one-time cost for a full destination-set refresh (~50 destinations × 300 POIs = 15,000 lookups): first 5,000/month free, then $17-32/1,000 depending on endpoint → **~$170-320 one-time**, near-zero after (ratings don't change fast). Deferred by cost decision, same bucket as BestTime.app/Booking.com. **Important limitation found**: the official API does **not** expose reviewer account age/review-count/Local-Guide level (that's Google Maps UI-only) — so "check how long this reviewer has been active" has no API equivalent; the feasible substitute when this gets built is rating-velocity/distribution-shape anomaly detection (sudden 5-star bursts, all-5-star or bimodal distributions) using data Place Details already returns.
- **TripAdvisor Content API** — correcting an earlier assumption: this is actually **self-serve** (sign up at tripadvisor.com/developers, generate a key immediately, no partner-approval gate found in current docs), pay-as-you-go, and includes real review *text* (Google's cheaper tiers don't). Exact per-call rate isn't published without signing up — 15-minute task next session to pull the real rate card before sizing. Treat as similar cost tier to Google Places until priced.
- **X/Twitter API v2** — priced (Basic ≈ $200/mo for ~10-15k reads, Pro ≈ $5,000/mo — last-published figures, re-verify at developer.x.com) but a flat subscription regardless of usage plus a noisy firehose needing heavy filtering. Documented as evaluated, but Google Places/TripAdvisor look like better spend for the same budget.
- **Foursquare** — public docs have pivoted almost entirely to enterprise geospatial products; the old consumer tips/ratings "Personalization API" is marked Deprecated with no public price found. Needs a founder-level sales inquiry, not an engineering spike.
- **Yelp Fusion** (free, but weak non-US/India coverage — parked until US traffic matters), **Pinterest API** (free, but images/boards not ratings/review text — weak signal fit), **Atlas Obscura** (best "hidden gems" editorial fit of anything evaluated, but no public API — needs a 15-min ToS/robots.txt check before a cautious RSS-only add).

**❌ Rejected — no viable access path, won't revisit:**
- **Instagram** — Graph API only covers content you own; scraping public posts/hashtags/locations violates ToS and Meta actively pursues scrapers legally.
- **TikTok** — "Research API" is restricted to approved academic researchers only, not commercial products; scraping is blocked by heavy obfuscation and prohibited by ToS.
- **Zomato** — API closed to new developers since ~2019.
- **Swiggy** — no public API, no developer program.
- **MakeMyTrip / Yatra / Goibibo / Cleartrip** (India OTAs) — no self-serve developer APIs, consumer apps only.
- **Quora** (India travel Q&A volume is huge) — no content API, ToS prohibits scraping.

**Authenticity-scoring design** (applies to Reddit/YouTube now, Google Places later — the underlying concern: low review-count + high rating is equally the signature of a paid-review farm, not just a hidden gem): build a composite 0-1 weight per mention (not a binary include/exclude) from whatever each source's *official API* genuinely exposes — Reddit account age/karma via `/user/{username}/about.json` (free, one extra call per unique author, long-TTL cached), YouTube commenter channel age/subscriber count via batched `channels.list` (free, in-quota), plus temporal-clustering and duplicate-text penalties computed from data already retrieved (bounded CPU, same pattern as today's lexicon scan). No source — not even Google's official Places API — exposes reviewer tenure/review-history as a clean field; that's a Maps-UI-only feature, not worth scraping to replicate.

**India domestic-travel coverage findings** (main user cohort is Indian — checked the actual scraper code for gaps, not just the abstract source list above):
- **Real gap found**: `gems.py`'s sentiment source (`reddit.py`'s `SUBREDDITS` list — `["travel", "solotravel", "digitalnomad", "backpacking"]`) has **no India subreddit at all**, while a separate list in `itinerary_corpus.py` (`ITINERARY_SUBREDDITS`) already includes `"IndiaTravel"`. Zero-cost fix: add `IndiaTravel` (+ consider city subs) to `reddit.py`'s list.
- **Real gap found**: `gems.py`'s `_POSITIVE_WORDS`/`_NEGATIVE_WORDS` lexicon is English-only — authentic Hindi/Hinglish travel commentary (common in domestic-travel YouTube comments) currently contributes zero sentiment signal, silently. Needs a small hand-authored Hinglish/Hindi supplement.
- YouTube video discovery (above) needs India-specific query phrasing (e.g. "hidden places to visit in Jaipur") to actually surface India's large domestic vlog ecosystem, not just generic English queries.
- **Popularity-capped seed lists that should carry a deliberately larger India-specific subset** (OSM/Wikivoyage per-destination ingestion is already fully demand-driven/uncapped regardless of country — no change needed there): `KNOWN_DESTINATIONS` in `reddit.py` has only **11 India entries out of ~134 total** (missing Rishikesh, Udaipur, Jodhpur, Hampi, Leh, Manali, Pondicherry, and other tier-2/3 domestic-tourist towns that fall into `"general"` today and lose their signal); `WIKIVOYAGE_ITINERARY_TITLES` in `itinerary_corpus.py` has only 1 of 5 India-specific; any future YouTube discovery seed list should start with a larger India set from day one. Sequence this *after/alongside* the already-tracked `osm-poi-refresh-big-cities` fix (Mumbai/Delhi already hit the Overpass rate-limit wall) so newly-added domestic destinations don't hit it too.
- **LBB (Little Black Book)** — India-specific urban "hidden gems" discovery publication, closer editorial fit than Atlas Obscura for domestic trips, no public API — same ToS-check treatment as Atlas Obscura. **Thrillophilia** (India experiences/activities, review-driven) looks partner-gated like Viator/GetYourGuide — fold into the existing founder-blocked affiliate outreach rather than a new thread.

**Sequencing — hard gate, per explicit direction**: none of the above gets built yet. First step is folding this into the docs (this entry, plus targeted pointers added to PRD/system-design/rag-strategy/GTM/eval-set/STARTUP_EVALUATION — 2026-07-16), committing to `main`, then applying the same doc commit to `feat/frontend-scaffold`. Only after both are pushed does any engineering work start.

### 4. Reddit ingestion — blocked on Reddit's approval, no ETA

Confirmed broken in production too (403 on every scheduled run since the Cloud migration), not just a sandbox-network quirk. Reddit's API access process has tightened — no more instant self-serve script key. A dedicated bot account was registered and a written app-review request submitted 2026-07-16 covering both ingestion flows (6-hourly sentiment mining across r/travel, r/solotravel, r/digitalnomad, r/backpacking; monthly itinerary-example search additionally across r/IndiaTravel, r/JapanTravel). **Check if approval came through.** If yes: get the `client_id`/`client_secret` from the app's Developers-portal page, rewire `scrapers/reddit.py::ingest_reddit()` to OAuth2 (check what Reddit's approval response specifies — password-grant with the dedicated bot account vs. client-credentials).

### 5. E2E pinned-POI positive path — now unblocked, not yet run

London now has real OSM data (58 POIs) after this session's retry pass — the test deferred in the 2026-07-15 session can now actually run: London trip → "I'm a huge Harry Potter fan" → verify 📌 pins, in-place regen, diff chips render correctly. Also the themes-backstop path ("add some zen gardens to my trip").

### 6. E2E gems check — still blocked on Reddit (or unblocked by item 3's alternative source)

Crowd dial = Hidden Gems → 💎 with provenance requires real sentiment data, currently only from Reddit (item 4). If item 3's alternative source ships first, re-scope this check to that source instead.

### 7. Itinerary corpus — source pool still thin

Reran `ingest_itinerary_corpus()` this session against the corrected Cloud cluster: 0→1 doc (up from 0, but still thin). Planet D RSS now fails with a connection-reset error (a different failure mode than the earlier User-Agent 403 — worth investigating if this becomes a priority). Consider adding 1-2 more blog feeds to `scrapers/itinerary_corpus.py`'s source list if this becomes a priority — small free-tier pool (1 blog + 5 Wikivoyage titles + Reddit trip-reports, the last fully blocked) plus a strict `is_itinerary` extraction gate limits yield regardless.

### 8. Affiliate tracking — blocked on founder

Register Viator / GetYourGuide / Skyscanner affiliate programs and supply IDs. Link formats fixed since v10.20.0, so the code side is a small param-append in `BookingLinksSection.tsx` + `cityCodes.ts` coverage check.

### 9. Fix stale duplicate-signup test (found 2026-07-20, not caused this session)

`tests/integration/test_auth.py::test_signup_rejects_duplicate_email` asserts `detail == "Unable to sign up with these details."`, but `routers/auth.py::signup()` intentionally returns `"An account with this email already exists. Try logging in instead."` (per an explicit product-decision comment right above the raise). Either the test predates that product decision and just needs updating, or something regressed the other way — 15-minute check to confirm which, then fix the mismatched side.

### 10. Recalibrate the rest of the budget-estimator's hand-authored figures as real data points turn up

Only one cell has a real research anchor so far (budget-tier / mid_range: Bengaluru→Colombo flight fare, Sri Lanka food/stay costs — see v10.26.0). Everything else in `core/distance_pricing.py`'s `DISTANCE_BANDS` (regional/long-haul/ultra-long-haul) and `core/budget_estimator.py`'s `_COST_MATRIX` (moderate/premium destination tiers) was extrapolated to preserve ordering, not independently verified. Same method as this session: find a real fare/hotel/food-cost data point for a specific route or destination, anchor the nearest band/cell to it, nudge neighbours just enough to stay monotonic, document which cell is the real anchor vs. extrapolated.

### 11. Verify the stay/food RAG-grounding path actually fires once Reddit/Wikivoyage ingestion is unblocked

`core/budget_estimator.py`'s `_grounded_or_flat()` (via `core/cost_grounding.py::community_median_price_inr()`) is wired up and tested, but as of 2026-07-20 it's a no-op in production — verified live against the real Qdrant Cloud cluster that `wiki`/`reddit` collections have 0 points (`itinerary_corpus` has 1). Once item 4 (Reddit approval) lands and ingestion resumes, spot-check a few real wizard budget-recommendation conversations and confirm `stay_community_based`/`food_community_based` actually flip to `true` for at least some destinations, and that the extracted numbers look sane (not a regex false-positive from an unrelated dollar amount in a Reddit post).

## 🔧 Operational / hygiene items (carried over)

- **Implement Reddit destination-matching widening** (design in `docs/scaling-tech-challenges.md` §8 item 4, not yet done): `scrapers/reddit.py::_extract_destination()` still only recognizes names in the static `KNOWN_DESTINATIONS` list — should match against `destination_ingestion_state` instead now that it exists, so organically-mentioned destinations outside the curated set aren't silently dropped. Low priority until Reddit ingestion itself is unblocked (item 4).
- **Rate-limit new-destination cold starts** (design in `docs/scaling-tech-challenges.md` §8 item 5, not yet done): `ensure_destination_ingested()` has no per-IP/session cap on first-request ingestion cost yet — worth adding (e.g. max 5/hour) before any meaningful traffic growth, to guard against garbage input running up Overpass/Gemini spend.
- **Consider indexing other frequently-filtered payload fields** if new filter patterns get added elsewhere — the `destination` index fix this session was reactive (found via a test failure); a quick audit of any other `FieldCondition` usage would catch similar gaps proactively before they ship.
- `HIDDEN_GEM`/`PINNED` admin metrics once real traffic exists · optional §4U: point `run_rag_eval.py` at `retrieve_context()` (non-trivial — `retrieve_context()` takes a full `TripConfig`, not the golden dataset's simple query+destination shape; needs a schema refactor, not a quick swap).
- Windows gotcha: `git commit -m` with embedded double quotes breaks in PowerShell 5.1 — write message to a file, use `git commit -F`.
- Gotcha: always verify `settings.qdrant_url` isn't `:memory:` before trusting a local ingestion script's results — check `get_qdrant().get_collection(name).points_count` against the real cluster rather than assuming from prior session notes.

## 💰 Deferred by cost decision (revisit later)

- **BestTime.app live crowd-forecast layer** (paid API) — premium/B2B upsell candidate.
- **Booking.com affiliate accommodation pricing** — blocked on partner approval.

## 📋 Phase 2 preview (publish is done — Phase 2 can start once founder signs off on the piece)

Agent mode (branded PDF export, markup field, client-shareable link) · live budget grounding (Amadeus free tier, IRCTC fare tables) · hand-onboard 10 agents. Full detail + kill/go criteria in [GTM_STRATEGY.md](GTM_STRATEGY.md) §5.
