# Commercial launch: free/fair-use API inventory & paid-replacement plan

**Status:** research/catalogue, not yet actioned. Written 2026-08-19 in response to a
"what enterprise APIs will we need before commercial go-live" question. Consolidates
and cross-references three places this was already partially tracked
(`docs/NEXT_SESSION_TODO.md`'s 2026-07-22 pre-commercial-data-sources note,
`core/budget_estimator.py`'s module docstring, `docs/scaling-tech-challenges.md`'s
rate-limiting findings) into one end-to-end checklist covering *every* external
service the product depends on, not just pricing data.

## Why this matters

WanderPlanner is currently built almost entirely on **free-tier, fair-use, or
personal/non-commercial-licensed** external services. That was the right call for a
pre-revenue, invite-only build — free/keyless sources are what let the RAG corpus and
budget estimator exist at all without a funding round. But several of those sources'
own Terms of Service **only permit non-commercial use**, and several others are
**best-effort infrastructure with no SLA** that will not hold up under real signed-up
user traffic, regardless of ToS. Both categories are go-live blockers, but for
different reasons — this doc separates them and gives each a way forward.

## How to read the table

- **Blocker type:**
  - 🔴 **ToS-prohibited** — ships a hard legal/compliance risk the moment there is
    revenue or a paid product, independent of traffic volume. Must be swapped or
    licensed before charging anyone anything.
  - 🟠 **No commercial SLA** — legally fine to keep using even commercially, but
    rate-limited/best-effort infrastructure meant for hobby-scale traffic; will
    start failing (429s, blocks, degraded latency) once real user volume arrives.
    Needs upgrading, not removing.
  - 🟡 **Paid roadmap item, not yet built** — already documented as a future paid
    integration; included here so the full cost picture is in one place.
- **Paid replacement** is the officially documented commercial-tier product from the
  same vendor where one exists, since that's the lowest-migration-effort option (same
  data shape, same client code, just an API key + billing).

---

## 🔴 ToS-prohibited for commercial use — must remove/re-license before charging anyone

| Source | Used for | File | ToS restriction | Paid replacement | Est. cost |
|---|---|---|---|---|---|
| **Numbeo** (numbeo.com) | Premium-tier `food_per_day_pp` in the budget estimator's flat cost table | `core/budget_estimator.py` (`_COST_MATRIX`, see module docstring "PRE-COMMERCIAL-ONLY DATA SOURCES") | ToS requires a paid commercial **Data License** for any use beyond personal/academic — hand-picked figures are currently baked into source, not live-fetched | Numbeo's own commercial Data License (contact sales; no published self-serve price) | Unknown — needs a sales quote |
| **budgetyourtrip.com** | Moderate/premium-tier `stay_per_night_pp` | `core/budget_estimator.py` (`_COST_MATRIX`) | ToS prohibits commercial reuse outright, no paid tier offered at all | None published — must re-source entirely | N/A (no path to keep this source) |

**Already-compliant fallbacks wired in alongside both, ready to take over:**
Wikivoyage (CC BY-SA 3.0) and Inside Airbnb (CC BY 4.0) are both commercial-use-permitted
(with attribution) and already integrated as cross-checks — see
`core/budget_estimator.py`'s docstring for the specific reconstruction approach tried
for `stay_per_night_pp` (works for Paris, does **not** generalize across cities — see
`docs/NEXT_SESSION_TODO.md`'s 2026-07-22 entry for the full finding). **Recommended
path:** derive `stay_per_night_pp` from Inside Airbnb (already licensed, already
ingested, has genuine city-level price data) rather than re-deriving a Wikivoyage
multiplier that didn't generalize; for `food_per_day_pp`, either license Numbeo
commercially (simplest, known figures) or extend the existing Wikivoyage-grounded
per-meal reconciliation (`_FOOD_MEALS_PER_DAY`, already partially live per
`docs/PRD.md`'s v10.37 note) enough to retire the flat premium-tier numbers entirely.

---

## 🟠 Free/best-effort infra with no commercial SLA — will not survive real traffic

| Source | Used for | File(s) | Current limit | Paid replacement | Est. cost |
|---|---|---|---|---|---|
| **Nominatim** (nominatim.openstreetmap.org) | All destination/place geocoding (wizard destination input, POI resolution, ingestion) | `apps/api/services/geocode.py` | Hard **1 req/sec**, no SLA, donated infra — 403s under load, confirmed live 2026-07-20 needing a compliant User-Agent | **Google Geocoding API** (Maps Platform) or a self-hosted Nominatim instance (full OSM planet or country-extract) | Google: ~$5/1,000 requests after $200/mo free credit. Self-hosted: no per-call fee, but dedicated server + ongoing OSM data-sync ops cost |
| **Overpass API** (overpass-api.de) | POI ingestion per destination (`ensure_destination_ingested` cold-start path) | `apps/api/scrapers/osm.py` | Free public service, rate-limited by load; 429/504 congestion errors already handled with retry/backoff (`osm_ingest_delay_seconds`) | **Google Places API (New)** — Text Search Pro / Place Details Pro (already the documented roadmap replacement for the *ratings/review-count* signal below; the raw POI/location data itself could migrate here too) or self-hosted Overpass against a downloaded OSM extract | Google: Text Search Pro $32/1,000, Place Details Pro $17/1,000, first 5,000/mo free (figures from `docs/rag-strategy.md`) |
| **OSM tile server** (`tile.openstreetmap.org`) | Itinerary map rendering (Leaflet) | `apps/web/components/map/ItineraryMap.tsx` | Explicitly "donated servers, capacity is limited... no SLA... we may block access without notice" per the OSMF Tile Usage Policy | **Mapbox** or **MapTiler** hosted tiles (drop-in Leaflet `TileLayer` swap), or **Google Maps JavaScript API** if consolidating onto one paid vendor | Mapbox: 50,000 free tile loads/mo, then ~$0.50-5/1,000 depending on tier. MapTiler: similar free tier + paid plans |
| **Wikivoyage / Wikimedia API** (`en.wikivoyage.org`) | Destination content ingestion (Eat/See/Do/Sleep sections), country-level visa info | `apps/api/scrapers/wikivoyage.py`, `apps/api/scrapers/visa_info.py`, `apps/api/scrapers/itinerary_corpus.py` | Free, keyless, but governed by the Wikimedia Foundation User-Agent Policy — already got hard-403'd once for an inadequate User-Agent (`core/config.py` comment, 2026-07-20) | No commercial paid tier exists for Wikimedia content (it's CC BY-SA, free by design) — the risk here is **infra availability**, not licensing. Mitigate via a self-hosted Wikimedia mirror/dump if the live API becomes unreliable, not a paid API swap | N/A — content stays free; only mitigation is self-hosting |
| **Open-Meteo** (`archive-api.open-meteo.com`) | "Best time to visit" seasonal weather data | `apps/api/services/best_time.py` | Free tier = **non-commercial use only**, 10,000 calls/day, no uptime guarantee | Open-Meteo's own **Customer API** (`customer-api.open-meteo.com`) — same request/response shape, just an `&apikey=` param and a paid plan | Subscription-tier pricing via Stripe checkout at open-meteo.com/en/pricing (dedicated servers, no daily cap, includes commercial-use license) |
| **Frankfurter.app** (`api.frankfurter.app`) | Currency conversion (budget field currency detection + dashboard currency widget) | `apps/api/core/currency_convert.py`, `apps/web/components/dashboard/CurrencyWidget.tsx` | Free, keyless, open-source, explicitly commercial-use-permitted per its own docs — **not actually a blocker**, but has no formal SLA/support contract | Not required — Frankfurter itself states commercial use is fine; only concern is availability risk if the free public instance goes down. Frankfurter is open source and self-hostable if that ever matters | N/A — lowest-priority row here, listed for completeness |
| **Pexels API** | Hero photos for PDF export | `apps/api/services/pexels.py` | Free tier: 200 req/hour, 20,000 req/month, contactable for a higher limit "if you meet our API terms" | Pexels' own higher-limit grant (free, just requires an approval conversation) or a paid stock-photo API (**Unsplash+ API**, **Shutterstock API**) if Pexels declines | Pexels: free if approved. Unsplash/Shutterstock: paid, usage-based |
| **YouTube Data API v3** (`search.list`, `commentThreads.list`, `videos.list`) | Community-sentiment ingestion (comment mining), price-grounding narration, video-embed discovery | `apps/api/scrapers/youtube_comments.py`, `apps/api/scrapers/youtube_narration.py` | Free 10,000 units/day, but `search.list` has its own **separate 100-calls/project/day cap** that binds first (`core/config.py`) — this is the actual quota ceiling, already tracked and budgeted around | **YouTube Data API quota increase request** (Google Cloud Console form, free but requires justification/review) — there is no "paid tier" for this API; Google grants higher quota on request rather than selling it | Free if the quota-increase request is approved; no purchasable SKU |
| **Groq** (LLM fallback provider, `llm_provider=groq`) | Itinerary generation fallback when Gemini is unavailable/rate-limited | `apps/api/core/llm_client.py`, `apps/api/core/config.py` | Free tier caps around 30 req/min (per `docs/eval-set.md`'s COST-015 test case) — already has 429-handling/retry documented | **Groq's paid/dedicated-throughput tier** ("Groq on-demand" / dedicated capacity via Groq Cloud) | Usage-based per-token pricing, varies by model — check current Groq Cloud pricing at go-live time |

---

## 🟡 Already-documented paid roadmap items (not yet built, tracked for completeness)

These are already called out as future work in `docs/rag-strategy.md` /
`docs/NEXT_SESSION_TODO.md` — included here so this doc is the single place that
answers "what paid APIs does go-live need," without re-litigating decisions already
made elsewhere.

| Source | Would add | Cost (as last documented) |
|---|---|---|
| **Google Places API (New)** | Structured rating/review-count signal for the "hidden gem" detector (low review count + high rating); could also replace Overpass for raw POI data (see 🟠 table above) | First 5,000 calls/mo free, then Text Search Pro $32/1,000, Place Details Pro $17/1,000. Est. $170-320 one-time for a full ~50-destination re-ingestion, then infrequent |
| **TripAdvisor Content API** | Location details + up to 5 real reviews/photos per location | Self-serve sign-up (confirmed, no partner approval needed), exact per-call rate not yet priced — budget similar tier to Google Places until confirmed |
| **X/Twitter API v2** | Real-time disruption alerts (strikes, delays, closures) | Basic ≈$200/mo (~10-15k reads), Pro ≈$5,000/mo — flat subscription, last-published figures, lower priority than Places/TripAdvisor per existing docs |

---

## Suggested sequencing for a commercial go-live checklist

1. **Legal/compliance gate (blocking, do first):** re-source or license Numbeo and
   budgetyourtrip.com — these are the only entries where continuing to operate
   commercially without action is a ToS violation, not just a scaling risk.
2. **Traffic-scaling gate (blocking once real signed-up volume arrives):** Nominatim,
   Overpass, and the OSM tile server are the three most likely to visibly break first
   (rate-limit errors, map tiles failing to load) — budget for Google Geocoding/Places
   and a paid tile provider (Mapbox/MapTiler) before any paid-user marketing push.
3. **Quota-ceiling watch (monitor, act if it starts binding):** YouTube's
   `search.list` 100-calls/day cap and Groq's free-tier rate limit are both already
   guarded in code (budget/backoff logic exists) — no urgent swap needed, but track
   actual usage against the ceiling as traffic grows and file the Google quota-increase
   request proactively rather than reactively.
4. **Low-priority / no action needed:** Frankfurter (commercial use already permitted)
   and Wikimedia/Wikivoyage (content is free by license; only mitigation is
   self-hosting if the public API's availability becomes a problem, not a paid swap).

## Cross-references

- `core/budget_estimator.py` module docstring — canonical source for the exact
  Numbeo/budgetyourtrip.com figures and the Wikivoyage-multiplier research that didn't
  generalize.
- `docs/NEXT_SESSION_TODO.md`, 2026-07-22 entry ("decision: allow ToS-restricted
  sources pre-commercial; tracked for removal at launch") — original decision record.
- `docs/rag-strategy.md`, "Phase v1 — Premium, high-fidelity sources" table — pricing
  detail for the 🟡 paid-roadmap sources.
- `docs/scaling-tech-challenges.md` — the original "no rate limiting anywhere except
  a local Nominatim throttle" finding that this doc's 🟠 section builds on.
