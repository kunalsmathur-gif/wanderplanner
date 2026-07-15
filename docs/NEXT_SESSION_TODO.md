# Next-Session TODO — Post-Cloud-migration cleanup → Reddit approval → Phase 2

**Last updated:** 2026-07-16 (critical Qdrant payload-index fix + demand-driven ingestion + google-genai upgrade — see v10.24.0 in TECHNICAL_DOCUMENTATION.md §14 for full detail)
**Context:** A routine dependency-bump task (`google-genai` 1.2.0→2.10.0, dependabot PR #8) led to discovering that Qdrant Cloud has been silently rejecting every `destination`-filtered RAG query since the Cloud migration (2026-07-15) — meaning real research context has likely not been reaching the live LLM prompt at all, degrading itinerary quality invisibly (the failure was swallowed by the fallback chain, never surfaced as an error). **This is fixed in code but needs a Railway redeploy/restart to actually take effect in production** — see item 1 below, this is the most important thing to confirm next session.

---

## 🔴 Do this first — verify the production fix actually landed

1. **Confirm Railway has redeployed/restarted since this session's `core/qdrant.py` fix shipped.** The payload-index creation only runs once per process start (`_ensure_collections()`, called from `get_qdrant()` on first use). If Railway's process wasn't restarted after this commit, prod is still silently 400-ing on every filtered RAG query. Check via Railway dashboard deploy history, or logs for a fresh `_ensure_collections` run.
2. **Verify from Railway logs**: filter for `destination` or `Index required` — should see zero occurrences after the redeploy. If you still see 400s, the index creation itself needs debugging against the prod cluster (should be identical to what worked locally, but confirm the prod `QDRANT_URL`/`QDRANT_API_KEY` point at the same cluster used to verify this fix).
3. **Once confirmed live**, consider re-running (or waiting for) a few real itinerary generations and spot-checking whether the RAG context block actually contains real retrieved content now (vs. the "No pre-fetched research available" sentinel it would silently fall back to before).

## ⏭️ Remaining items (in suggested order)

### 1. Reddit ingestion — blocked on Reddit's approval, no ETA

Confirmed broken in production too (403 on every scheduled run since the Cloud migration), not just a sandbox-network quirk. Reddit's API access process has tightened — no more instant self-serve script key. A dedicated bot account was registered and a written app-review request submitted 2026-07-16 covering both ingestion flows (6-hourly sentiment mining across r/travel, r/solotravel, r/digitalnomad, r/backpacking; monthly itinerary-example search additionally across r/IndiaTravel, r/JapanTravel). **Check if approval came through.** If yes: get the `client_id`/`client_secret` from the app's Developers-portal page, rewire `scrapers/reddit.py::ingest_reddit()` to OAuth2 (check what Reddit's approval response specifies — password-grant with the dedicated bot account vs. client-credentials).

### 2. OSM POI coverage — 33 destinations still rate-limited (low priority)

Two retry passes (6s then 12s delay) got 105/134 destinations to real data (up from 48). The remaining ~33 (Bangkok, Mumbai, Delhi, Paris, London*, New York, etc. — see git history of `apps/api/scripts/retry_osm_ingest_pass2.py`'s `STILL_ZERO` list) are persistently Overpass-rate-limited even at 12s delay — a third pass hit diminishing returns and wasn't run. Real fix would need actual exponential backoff/longer delays (30s+) rather than more retries at the same cadence. *Note: London itself succeeded on pass2 (58 POIs) — the E2E test below is unblocked.

### 3. E2E pinned-POI positive path — now unblocked, not yet run

London now has real OSM data (58 POIs) after this session's retry pass — the test deferred in the 2026-07-15 session can now actually run: London trip → "I'm a huge Harry Potter fan" → verify 📌 pins, in-place regen, diff chips render correctly. Also the themes-backstop path ("add some zen gardens to my trip").

### 4. E2E gems check — still blocked on Reddit

Crowd dial = Hidden Gems → 💎 with provenance requires real `reddit` collection data, which requires item 1 above (Reddit ingestion) to be unblocked first.

### 5. Itinerary corpus — source pool still thin

Reran `ingest_itinerary_corpus()` this session against the corrected Cloud cluster: 0→1 doc (up from 0, but still thin). Planet D RSS now fails with a connection-reset error (a different failure mode than the earlier User-Agent 403 — worth investigating if this becomes a priority). Consider adding 1-2 more blog feeds to `scrapers/itinerary_corpus.py`'s source list if this becomes a priority — small free-tier pool (1 blog + 5 Wikivoyage titles + Reddit trip-reports, the last fully blocked) plus a strict `is_itinerary` extraction gate limits yield regardless.

### 6. Affiliate tracking — blocked on founder

Register Viator / GetYourGuide / Skyscanner affiliate programs and supply IDs. Link formats fixed since v10.20.0, so the code side is a small param-append in `BookingLinksSection.tsx` + `cityCodes.ts` coverage check.

## 🔧 Operational / hygiene items (carried over)

- **Implement Reddit destination-matching widening** (design in `docs/scaling-tech-challenges.md` §8 item 4, not yet done): `scrapers/reddit.py::_extract_destination()` still only recognizes names in the static `KNOWN_DESTINATIONS` list — should match against `destination_ingestion_state` instead now that it exists, so organically-mentioned destinations outside the curated set aren't silently dropped. Low priority until Reddit ingestion itself is unblocked (item 1).
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
