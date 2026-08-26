# Plan: India Workation & Long Weekend Finder

## Problem

WanderPlanner's existing flow requires a user to already know a destination (or at least
a theme) before the wizard can help. The target cohort here is different: Indian corporate
employees who (a) don't know where to go, (b) don't track upcoming long weekends / optimal
leave days, (c) don't know what's happening around India that matches their interests, and
(d) need workation logistics (WFH-friendly wifi in cafes/hotels) for a hybrid "5 days WFH +
2 weekend days exploring" trip shape.

Per user decisions, this ships as a **new standalone surface** — `/workation` — with its own
entry point on the landing page, separate from the Anya wizard. It is a discovery/decision
layer: "given your home state, interests, and leave budget, here are 3–5 long-weekend windows
and destinations that fit, plus the workation logistics for each." A user can then optionally
hand off a chosen destination + dates into the existing wizard to generate a full itinerary
(reusing existing generation, not duplicating it).

## Decisions locked in with the user

- **Surface**: standalone page/route (not folded into the wizard or Digital Nomad persona).
- **Holiday data**: static/curated India national + state-wise gazetted holiday calendar,
  refreshed periodically (matches the existing Wikivoyage/OSM "static + periodic refresh"
  pattern already used for visa/safety data) — no paid holiday API.
- **Events data**: new dedicated pan-India events ingestion source (curated events
  calendar), distinct from and in addition to the existing Epic 4 signals
  (Wikivoyage/Wikipedia/OSM/Reddit/YouTube), which remain for per-destination seasonal
  narrative.
- **Workation-friendly venues**: no new data source — infer from existing accommodation/
  property data plus OSM cafe tags (`internet_access=wlan|yes`, `wifi=yes`, etc.), same
  scraper already used for POIs (`apps/api/scrapers/osm.py`).

## Proposed user-facing shape

A single curated page, personalized by two inputs the user gives once (home state/city +
interests, reusing existing persona/interest vocabulary where possible):

> "Because you work out of Karnataka, here are your upcoming long weekends: Nov 14–16
> (Kanataka Rajyotsava + weekend, 1 leave day needed). Around that time in India: [events
> matching music/culture]. Based on your interests, here's where this works best: Hampi,
> Gokarna, Coorg — each with a suggested 5-WFH + 2-weekend workation split, and cafes/
> hotels with verified wifi for your WFH days."

Core components of the view:
1. **Long weekend finder** — for the user's state, list upcoming long weekends (calendar
   gaps combining national + state holidays + weekends), each annotated with "N leave
   days needed for M days off."
2. **What's happening** — events around each long-weekend window, filtered by the user's
   selected interests (music, culture, etc.), pan-India (not one destination).
3. **Destination shortlist** — for the top-ranked long weekend + interests, a short list of
   candidate destinations with a fit rationale.
4. **Workation logistics per destination** — the 5 WFH-day / 2 weekend-day split, and a
   short list of wifi-verified cafes/hotels.
5. **Hand-off CTA** — "Plan this trip" sends the chosen destination + date range into the
   existing wizard/generation flow (pre-filling required fields) rather than re-implementing
   itinerary generation.

## Backend work (apps/api)

- **New static dataset**: India holiday calendar (national + all states/UTs), stored as a
  versioned JSON/CSV under `apps/api/services/data/` (same pattern as
  `common_english_words.txt`), covering at least the current + next calendar year, with a
  documented periodic-refresh process (similar to how Wikivoyage/visa data is refreshed).
- **New service**: `services/long_weekend.py` — given a state + date range, computes
  candidate long-weekend windows (holiday + weekend adjacency, leave-days-needed count),
  ranked by "best value" (most days off per leave day used).
- **New ingestion source**: `scrapers/india_events.py` — pan-India events feed, sourced in
  priority order (official APIs first, curated static data second, scraping/affiliate only
  as fallback — no single feed covers sports + music + food + culture + pilgrimage + crafts):
  - **Primary — official developer APIs, no scraping or affiliate deal needed**:
    - **AllEvents.in API** (free tier) — India-focused aggregator purpose-built for this
      exact "what's happening near me by interest/date" need: concerts, comedy, workshops,
      cultural events, meetups across Indian cities. Main workhorse source.
    - **Eventbrite API** (official, free tier) — workshops, conferences, meetups, some
      cultural events; decent India coverage, very low legal/ToS risk.
    - **Bandsintown Artist Events API** (official, free) — supplements music tour/concert
      dates specifically.
    - (Meetup's API is now paid-only/Pro-tier — deprioritized on cost grounds, revisit
      later if the free sources leave gaps in workshop/hobbyist coverage.)
  - **Tier A — curated annual calendar** (static, refreshed once a year, same pattern as
    the holiday dataset), for categories the APIs above don't cover well: pilgrimage and
    major fixed/lunar-calendar cultural festivals (Kumbh Mela cycle, Char Dham Yatra
    open/close, Rath Yatra, Pushkar Mela, Durga Puja, regional Diwali-adjacent festivals)
    curated from Ministry of Tourism (incredibleindia.gov.in), ICCR/Sangeet Natak
    Akademi/NCPA public calendars, state tourism boards, and individual temple trust
    sites (e.g. Tirumala Tirupati Devasthanams, Vaishno Devi Shrine Board); plus major
    sports league *windows* (IPL/ISL/Pro Kabaddi months), predictable enough without
    live fixtures.
  - **Tier B — periodic scrape/ingest fallback** (only for gaps the API/curated sources
    leave, e.g. regional food festivals, craft workshops): Wikipedia festival list pages,
    state tourism "upcoming events" pages, and Dastkari Haat Samiti / state handicraft
    board listings, cached the same way `itinerary_corpus.py`/`wikivoyage.py` cache their
    scraped data, treated as lowest-confidence/best-effort.
  - **Optional secondary enhancement — BookMyShow affiliate feed** (concerts/comedy/
    theatre): BookMyShow has no public API and its ToS prohibits scraping, so if the
    official APIs above don't give enough concert/comedy coverage, integrate via a
    commercial **affiliate network** (e.g. Admitad/Vcommission or BookMyShow's own
    affiliate program) for a structured feed + trackable deep-links — mirrors the
    existing flight/hotel deep-link pattern (Skyscanner/Booking.com, Epic 5). **This is a
    business/commercial step (affiliate sign-up + ToS acceptance), not pure engineering**
    — sequenced after the primary API sources, only pursued if a real coverage gap
    remains. Klook (skews to activities/attraction tickets, not festivals) and Zomato
    District (no public API or affiliate feed currently available) were evaluated and are
    **not** pursued for now; revisit if Zomato District opens a partner API.
  - Every event record carries: name, date range, location, an **interest-category tag**
    (music/food/culture/pilgrimage/sports/craft), a **source citation**, and — for
    affiliate-sourced records — a deep-link. Same provenance discipline as the existing
    hidden-gems feature applies throughout: never surface an event without a traceable
    source; if no matching event exists for an interest/window, show "nothing found"
    rather than fabricate one.
  - **RAG-refinement layer — batch-ingested corpus, not fetched live** (reuses the
    existing Qdrant RAG infrastructure and its periodic-ingestion cadence, e.g. OSM's
    weekly job, rather than adding new real-time calls): a new `india_events` Qdrant
    collection, embedded with the same `all-MiniLM-L6-v2` model already used for
    `wiki`/`osm_pois`/`youtube_comments`, populated on a weekly/monthly batch cycle from
    sources that don't need to be live because event announcements lead time is weeks to
    months:
    - **Wikipedia** festival/category pages (`Category:Festivals in India`, `Category:
      Recurring sporting events established in India`) and city "Tourism in X" pages.
    - **Wikivoyage "Events" sections** — already scraped per-destination for Epic 4; the
      same scrape output gets a second write into `india_events` tagged pan-India,
      instead of building a separate scraper.
    - **Sahapedia** (Indian arts/culture encyclopedia) for cultural/craft context and
      provenance-rich descriptions.
    - **PIB (Press Information Bureau) Ministry of Culture/Tourism releases** and state
      tourism board sites — official, low ToS risk, good for pilgrimage/cultural
      announcements.
    - **News RSS feeds** (e.g. Times of India Events section, city-desk sections of major
      outlets) for time-bound one-off announcements (food festivals, pop-up craft
      bazaars) that Wikipedia/Wikivoyage won't have.
    - **Automation**: fully automated, no manual step — a new `_refresh_india_events` job
      function added to `core/scheduler.py`, wired into `start_scheduler()` exactly like
      `_refresh_osm_pois`/`_refresh_youtube_comments`/`_refresh_visa_info`/
      `_refresh_itinerary_corpus` already are. It runs automatically for as long as the
      API process is up (wired via `main.py`'s app lifespan calling `start_scheduler()`
      on boot) — the `scripts/` directory's `reingest_*.py` one-offs are only for manual
      backfills/corrections, not the regular cadence. Same caveat as the existing jobs:
      this assumes a single long-running API instance — if the deployment scales to
      multiple instances, each would duplicate-run the job, which is a pre-existing
      assumption in the codebase, not something new introduced here.
    - **Reliability pattern (updated 2026-08-26)**: a scheduler cadence bug was found and
      fixed while implementing this plan — `IntervalTrigger` alone resets its countdown on
      every deploy/restart, because APScheduler's in-memory job store computes next-fire
      time from process-start, not from actual last-successful-run. `_refresh_india_events`
      should follow the now-corrected pattern, not the plain `IntervalTrigger` originally
      described above:
      - **Deploy-safe cadence**: gate via the new `core/job_run_state.py` helpers
        (`is_due()`/`mark_ran()`), backed by the `job_run_state` DB table (job_id →
        last_run_at), so the 7-day interval is measured from the last real successful run,
        independent of how many times the process has restarted in between.
      - **Off-peak scheduling**: register with a `CronTrigger(hour=2|3, ..., timezone=
        ZoneInfo("Asia/Kolkata"))` via the `_off_peak_ist()` helper, staggered alongside the
        existing 02:00/02:20/02:40/03:00/03:20 IST jobs, instead of an arbitrary-time
        `IntervalTrigger` — keeps ingestion load off the 2-4AM IST off-peak-only window so
        no user is impacted.
      - **Exponential backoff on failure**: wrap the actual ingestion call(s) with
        `core/retry.py`'s `with_backoff()` so a transient failure (network blip, API
        hiccup) gets a few same-night retries with doubling delay (capped by
        `max_total_delay_seconds` so retries can never spill into peak hours) instead of
        silently waiting a full 7 days for the next attempt. On exhaustion, don't call
        `mark_ran()` — the job is retried automatically at tomorrow's off-peak run rather
        than waiting the full cadence again.
      - See `apps/api/core/scheduler.py`, `apps/api/core/job_run_state.py`,
        `apps/api/core/retry.py`, and their tests (`tests/unit/test_job_run_state.py`,
        `tests/unit/test_retry.py`) for the reference implementation already applied to
        `_refresh_reddit`, `_refresh_itinerary_corpus`, `_refresh_visa_info`,
        `_refresh_osm_pois`, and `_refresh_youtube_comments`.
    - **Existing `youtube_comments`/`youtube_narration` collections** — mined for event/
      festival name mentions the same way `services/gems.py` already extracts
      mention-based signals, adding an event-tag extraction pass rather than a new
      ingestion pipeline. (Reddit is **not** used here — it was retired product-wide on
      2026-07-26 per `docs/rag-strategy.md`; do not reintroduce it as a source.)
    - **AllEvents.in / Eventbrite / Bandsintown / Meetup APIs — also batch-pulled, not
      only queried live**: the same official APIs listed under "Primary" above are additionally
      polled on the weekly/monthly batch cycle (broad city/interest sweeps rather than a
      per-user live call) and their results embedded into `india_events` too, so upcoming
      listings are already in the corpus before a user ever asks. This means most requests
      are served entirely from the pre-embedded corpus at near-zero cost; a live call to
      these APIs is only made as a top-up when the corpus is stale or thin for a specific
      window (e.g. an event added to the platform after the last batch run). Meetup is
      included here despite its paid Pro-tier API specifically *because* batch-pulling
      periodically (not per-request) makes the cost bounded and predictable rather than
      scaling with traffic — worth revisiting once real usage volume is known.
    - At query time, this collection is retrieved semantically (interest + date-window +
      location as the query embedding) via the same `retrieve_context()`-style pattern
      already used elsewhere — no live scrape or API call per user request in the common
      case. Live calls to AllEvents.in/Eventbrite/Bandsintown (and the optional BookMyShow
      affiliate feed) are reserved for the narrow "on sale now" freshness top-up case
      described above: the RAG corpus supplies breadth cheaply, live sources supply
      freshness only where it actually matters.
- **New service**: `services/workation_venues.py` — extends the OSM scraper's cafe/hotel
  queries to add wifi/internet_access tag filtering, and cross-references existing
  accommodation data already used for property specs, to produce a "workation-friendly"
  venue shortlist per destination.
- **New chain**: `chains/workation_recommend_chain.py` — combines long-weekend windows +
  events + interests to rank and explain destination candidates (mirrors the existing
  `recommend_cities_chain.py` pattern for LLM-assisted ranking/rationale text).
- **New router**: `routers/workation.py` exposing:
  - `GET /api/workation/long-weekends?state=Karnataka` → ranked long-weekend windows
  - `POST /api/workation/recommend` → `{state, interests, date_range?}` → ranked
    destinations + rationale + events + venue shortlist per destination
  - Follows the same auth/rate-limit/analytics conventions as `recommend_cities.py`
    (`get_optional_user`, `LLM_RATE_LIMIT`, `flush_llm_usage`, `sanitize_error`).
- **Analytics**: log a new event family (e.g. `workation_view`, `workation_recommend`,
  `workation_handoff`) into the existing generic `events` table — no new table needed.

## Frontend work (apps/web)

- **New route**: `app/workation/page.tsx` (+ supporting layout if needed), linked from a
  new CTA/card on the landing page (`app/page.tsx`).
- **New components** under `components/workation/`:
  - `HomeStateInterestForm` — lightweight one-time input (home state/city + interest
    chips, reusing existing chip components where possible).
  - `LongWeekendList` — cards showing each upcoming long weekend with leave-days-needed.
  - `EventsAroundYou` — events matching interests within the selected window.
  - `DestinationShortlist` — ranked destination cards with rationale text.
  - `WorkationLogistics` — 5 WFH-day / 2 weekend-day split + wifi-verified venue list per
    destination.
  - `PlanThisTripCTA` — hands off destination + dates into existing wizard state
    (reusing the existing "pending-generation resume" pattern already built for
    signup/login round-trips, per PRD Epic 1A).
- **API client**: add `getLongWeekends`/`getWorkationRecommendations` calls in
  `apps/web/lib/api.ts`, following existing SSE/fetch conventions.
- **Types**: add shared request/response types to `packages/types` if it's used for
  cross-app contracts (check existing usage before adding).

## Data/quality notes

- Long-weekend computation is pure date math once the holiday calendar exists — no LLM
  needed, low cost, deterministic and testable.
- Events data must carry interest tags and be honest about coverage gaps (an interest
  with zero matching events near a given window should show "nothing found" rather than
  a fabricated placeholder — consistent with the existing hidden-gems "never invent a
  recommendation" principle in the PRD).
- Wifi/internet_access OSM tagging is sparse in India; the venue shortlist should degrade
  gracefully (fewer venues shown, or a disclaimer) rather than fabricate coverage, and
  should visibly cite provenance (OSM tag) similar to the existing "mentioned in N
  traveller posts" provenance pattern for hidden gems.
- International trips are out of scope for this surface (workation cohort is domestic per
  the ask); state holidays are India-specific.

## Suggested build sequence (todos tracked in SQL)

1. India holiday calendar dataset + long-weekend computation service (backend, no LLM,
   independently testable).
2. Pan-India events ingestion scraper + cache.
3. Workation-friendly venue signal (OSM wifi tags + existing accommodation data).
4. Recommendation chain + router tying 1–3 together.
5. Frontend `/workation` page + components, wired to the new endpoints.
6. Hand-off integration into existing wizard pending-generation flow.
7. Analytics events + docs update (PRD Epic addition, ADR if the design choices here
   warrant one).

## Open items intentionally left for implementation time (not blocking this plan)

- Exact curated events-calendar source to scrape (pick during step 2, evaluate ToS like
  the existing Reddit/Instagram/TikTot evaluations already documented in
  `docs/NEXT_SESSION_TODO.md`).
- Exact list of Indian states/UTs holiday data granularity (e.g. handling union
  territories, regional optional holidays) — resolve during dataset creation.
- Whether "Plan this trip" hands off into wizard Step 1 or skips to Step 2 (Itinerary
  Overview) — decide once wizard pre-fill code is inspected during implementation.
