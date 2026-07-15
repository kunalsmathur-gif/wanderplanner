# Next-Session TODO — Post-Cloud-migration cleanup → Reddit approval → Phase 2

**Last updated:** 2026-07-16 (critical Qdrant payload-index fix + demand-driven ingestion + google-genai upgrade — see v10.24.0 in TECHNICAL_DOCUMENTATION.md §14 for full detail)
**Context:** A routine dependency-bump task (`google-genai` 1.2.0→2.10.0, dependabot PR #8) led to discovering that Qdrant Cloud has been silently rejecting every `destination`-filtered RAG query since the Cloud migration (2026-07-15) — meaning real research context has likely not been reaching the live LLM prompt at all, degrading itinerary quality invisibly (the failure was swallowed by the fallback chain, never surfaced as an error). **This is fixed in code but needs a Railway redeploy/restart to actually take effect in production** — see "Do this first" below. The user is targeting a POC round of real testers soon; items 1-3 in the "Remaining items" list below are what came out of a 2026-07-16 discussion about what's actually needed before that.

---

## 🔴 Do this first — verify the production fix actually landed

1. **Confirm Railway has redeployed/restarted since this session's `core/qdrant.py` fix shipped.** The payload-index creation only runs once per process start (`_ensure_collections()`, called from `get_qdrant()` on first use). If Railway's process wasn't restarted after this commit, prod is still silently 400-ing on every filtered RAG query. Check via Railway dashboard deploy history, or logs for a fresh `_ensure_collections` run.
2. **Verify from Railway logs**: filter for `destination` or `Index required` — should see zero occurrences after the redeploy. If you still see 400s, the index creation itself needs debugging against the prod cluster (should be identical to what worked locally, but confirm the prod `QDRANT_URL`/`QDRANT_API_KEY` point at the same cluster used to verify this fix).
3. **Once confirmed live**, consider re-running (or waiting for) a few real itinerary generations and spot-checking whether the RAG context block actually contains real retrieved content now (vs. the "No pre-fetched research available" sentinel it would silently fall back to before).

## ⏭️ Remaining items (in suggested order — items 1-3 are POC-readiness priorities per 2026-07-16 discussion)

### 1. Security checks before any real (even POC) traffic

Not reviewed this session — needs a fresh pass before opening the app to real testers, even a small POC group. `docs/scaling-tech-challenges.md`'s risk-tiering table has a "Now (any traffic)" bucket that should be re-verified against current code, not assumed still valid: SSRF protection on `extract-trip`'s URL-fetching path, rate limiting on LLM-calling endpoints, sanitized error responses (no raw provider stack traces reaching the client — `core/errors.py::sanitize_error()` exists, confirm it's applied everywhere it should be), pinned dependencies + dependency/secret scanning in CI, structured logging/basic observability (Sentry/APM) so a POC session's failures are actually visible. Also worth a quick check that no secrets leaked into git history from this session's `.env` edits (they shouldn't have — `.env` is gitignored and nothing in the diff touched it — but worth a `git log -p -- apps/api/.env` sanity check).

### 2. Refresh OSM POI data for big cities before POC (elevated priority — was "low priority," now tied to POC quality)

Paris, Mumbai, Delhi, Bangkok, New York, and ~28 others are still missing real OSM data (persistently Overpass-rate-limited even at 12s delay across two retry passes — see `apps/api/scripts/retry_osm_ingest_pass2.py`'s `STILL_ZERO` list in git history for the exact set). These are exactly the destinations POC testers are statistically most likely to try, and without real POI grounding those itineraries lean more on the LLM's own knowledge (still generates fine, just a weaker showcase of the "verified real places" value prop). Needs actual exponential backoff / longer delays (30s+, possibly a dedicated slower job run over a longer window) rather than more retries at the same 12s cadence, which already hit diminishing returns.

### 3. Hidden gems — alternative data source if Reddit approval doesn't come through in time

Reddit's approval has no ETA (see item 4 below), so the "hidden gems" feature (`services/gems.py`) currently has zero real sentiment data to work with — it degrades gracefully (empty result) but isn't demo-able for a POC. Worth researching a fallback/parallel data source that doesn't depend on Reddit approval, so this differentiator has *something* to show even if Reddit stays blocked. Candidate directions to evaluate next session (not yet researched in depth):
- **YouTube video transcripts** — already a free-tier source used elsewhere (`itinerary_corpus` ingestion via `youtube-transcript-api`, already a pinned dependency) — travel vlogger transcripts could be mined for the same "specific place mentioned + sentiment" signal `gems.py` currently extracts from Reddit chunks, reusing the same lexicon-based scoring logic.
- **Wikivoyage "see/do" text** (already ingested, no new source needed) — lacks Reddit's community-mention-volume signal (can't distinguish "hidden gem" from "crowd favourite" without a mention-frequency proxy), but could seed a simpler always-available baseline layer.
- **Instagram/TikTok** — likely hits the same anti-scraping wall Reddit did; probably not worth pursuing given this session's Reddit experience, but worth a 5-minute sanity check before ruling out.
- Whatever direction is chosen, keep the existing "zero mentions = never recommend" honesty guarantee — no hallucinated gems, real provenance always attached.

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
