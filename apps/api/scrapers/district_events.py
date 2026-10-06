"""District.in (Zomato) headless-browser event scraper.

District.in's events listing is a client-rendered React SPA — a plain HTTP
GET only returns an empty shell (confirmed 2026-10-05: city sub-pages
404, and the root page loads but carries no event data without JS
execution). There's no public RSS/API either. The site's own frontend
resolves a visitor's city from the browser's geolocation and then calls an
internal `get_discovery_results` endpoint to populate the page — so getting
real data requires actually running the page's JavaScript in a real
browser, unlike every other scraper in `scrapers/india_events.py` (which
are all plain `httpx` GETs).

This makes the module a materially heavier/different operational posture
than the rest of `scrapers/`: a full headless Chromium process per city,
not a single HTTP request. Kept in its own module (rather than inlined
into `india_events.py`) so the `playwright` dependency stays isolated —
`ingest_india_events()` only calls this if the import succeeds, degrading
to a no-op otherwise (so a missing/not-yet-installed Playwright browser
never breaks the rest of the ingest).

Approach confirmed live 2026-10-05: set a Playwright browser context's
`geolocation` to a target city's coordinates, navigate to
`district.in/events/`, and capture the JSON the page's own code requests
from `get_discovery_results` (richly structured: name, start/end epoch,
venue, city, slug — no need to additionally visit each individual event
page). Architecture is inspired by the general "render, then parse
structured results" idea used by other open-source India-events scrapers
(e.g. rixav77/srishti's two-phase scraper concept) but written
independently against District.in's actual, reverse-engineered
request/response shape — no code copied from any other project.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from scrapers.india_events import EventRecord, _guess_category

logger = logging.getLogger(__name__)

_IST = ZoneInfo("Asia/Kolkata")

# Seed coordinates per city — these are only used to resolve District.in's
# own city context (via injected browser geolocation), not stored as event
# coordinates themselves (each event's own venue_name/city from the
# response is used for that).
#
# Expanded 2026-10-06 from the original 7 metros to cover every city in
# `scrapers.india_events._INGEST_DEFAULT_CITIES` (all states/UTs), after
# live-verifying District.in returns real events for non-metro cities too
# (e.g. Jaipur 32 events, Lucknow 31, Indore 32 — confirmed live, not
# assumed). Coordinates are standard public city-center lat/lon (not
# derived from any user/private data).
_DISTRICT_CITY_COORDS: dict[str, tuple[float, float]] = {
    "Mumbai": (19.0760, 72.8777),
    "Delhi": (28.6139, 77.2090),
    "Bengaluru": (12.9716, 77.5946),
    "Hyderabad": (17.3850, 78.4867),
    "Chennai": (13.0827, 80.2707),
    "Kolkata": (22.5726, 88.3639),
    "Pune": (18.5204, 73.8567),
    "Ahmedabad": (23.0225, 72.5714),
    "Jaipur": (26.9124, 75.7873),
    "Surat": (21.1702, 72.8311),
    "Lucknow": (26.8467, 80.9462),
    "Kanpur": (26.4499, 80.3319),
    "Nagpur": (21.1458, 79.0882),
    "Indore": (22.7196, 75.8577),
    "Bhopal": (23.2599, 77.4126),
    "Visakhapatnam": (17.6868, 83.2185),
    "Patna": (25.5941, 85.1376),
    "Vadodara": (22.3072, 73.1812),
    "Ludhiana": (30.9010, 75.8573),
    "Agra": (27.1767, 78.0081),
    "Nashik": (19.9975, 73.7898),
    "Varanasi": (25.3176, 82.9739),
    "Srinagar": (34.0837, 74.7973),
    "Amritsar": (31.6340, 74.8723),
    "Prayagraj": (25.4358, 81.8463),
    "Ranchi": (23.3441, 85.3096),
    "Jodhpur": (26.2389, 73.0243),
    "Coimbatore": (11.0168, 76.9558),
    "Guwahati": (26.1445, 91.7362),
    "Mysuru": (12.2958, 76.6394),
    "Thiruvananthapuram": (8.5241, 76.9366),
    "Kochi": (9.9312, 76.2673),
    "Madurai": (9.9252, 78.1198),
    "Puri": (19.8135, 85.8312),
    "Udaipur": (24.5854, 73.7125),
    "Pushkar": (26.4896, 74.5509),
    "Shillong": (25.5788, 91.8933),
    "Gangtok": (27.3389, 88.6065),
    "Leh": (34.1526, 77.5771),
    "Shimla": (31.1048, 77.1734),
    "Dehradun": (30.3165, 78.0322),
    "Panaji": (15.4909, 73.8278),
    "Bhubaneswar": (20.2961, 85.8245),
    "Raipur": (21.2514, 81.6296),
    "Jammu": (32.7266, 74.8570),
    "Kozhikode": (11.2588, 75.7804),
    "Thrissur": (10.5276, 76.2144),
    "Hampi": (15.3350, 76.4600),
    "Ajmer": (26.4499, 74.6399),
    "Bikaner": (28.0229, 73.3119),
    "Jaisalmer": (26.9157, 70.9083),
    "Nagaur": (27.2000, 73.7333),
    "Kullu": (31.9570, 77.1095),
    "Manali": (32.2432, 77.1892),
    "Haridwar": (29.9457, 78.1642),
    "Rishikesh": (30.0869, 78.2676),
    "Mathura": (27.4924, 77.6737),
    "Vrindavan": (27.5820, 77.7000),
    "Konark": (19.8876, 86.0945),
}

# Bounded concurrency for `fetch_district_events_batch`'s contexts sharing
# one browser — keeps District.in from receiving dozens of simultaneous
# navigations at once while still letting a 58-city sweep finish quickly
# (one shared browser removes the dominant per-city Chromium-launch cost;
# this just bounds how many page navigations run in parallel at a time).
_DISTRICT_BATCH_CONCURRENCY = 4

_DISTRICT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
_DISTRICT_EVENTS_URL = "https://www.district.in/events/"
_DISTRICT_PAGE_TIMEOUT_MS = 30_000
_DISTRICT_RESPONSE_TIMEOUT_S = 15.0
# Raised from an earlier 20 after a real coverage gap was found live
# (2026-10-06): the single `get_discovery_results` response already
# contains *every* rail (Trending, Dandiya/Garba, Comedy, Sports, Food,
# etc.) and all of their items in one page load — this cap only truncates
# how much of that *already-fetched* response we keep, it does not trigger
# any additional browser navigation or network request. A low cap meant
# whichever rail happened to be iterated first (observed live: a
# currently-in-season "Dandiya/Garba" rail) silently consumed the entire
# budget before the loop ever reached rails for other interest categories
# (sports/food/pilgrimage/non-Dandiya music) — confirmed live: 139 of 157
# District.in-sourced events in the production dataset were tagged
# "culture" versus single digits for every other category.
#
# This value (60) is empirically grounded, not a round-number guess: a
# live probe (2026-10-06) of the actual `get_discovery_results` response
# across all 7 cities `ingest_india_events()` covers found 31-49 total
# `EventData` items per city (Mumbai 35, Delhi 40, Bengaluru 41,
# Hyderabad 35, Chennai 31, Kolkata 49, Pune 35) — i.e. one page load
# never contains more than ~50 real events regardless of city. 60 gives
# headroom above the observed max (49) so the cap never actually binds
# today, while still being a real, intentional ceiling (not "infinity")
# in case a city's response ever grows unexpectedly large. Re-probe if a
# future session suspects this has drifted.
_DISTRICT_MAX_EVENTS_PER_CITY = 60


async def _fetch_one_city_with_browser(browser: Any, city: str) -> list[EventRecord]:
    """Shared per-city fetch logic: open one browser context against an
    already-running `browser`, resolve District.in's city context to `city`
    via injected geolocation, navigate to its events listing, and parse the
    structured event items out of the page's own `get_discovery_results`
    response. Factored out of `fetch_district_events`/
    `fetch_district_events_batch` so both single- and multi-city callers
    share one implementation.

    Never raises: a navigation/timeout failure or a malformed response
    degrades to `[]`, the same best-effort contract as every fetcher in
    `scrapers/india_events.py`. Returns `[]` immediately for a city with no
    seed coordinate in `_DISTRICT_CITY_COORDS` (no reliable way to resolve
    its location context).
    """
    coords = _DISTRICT_CITY_COORDS.get(city)
    if coords is None:
        return []

    lat, lon = coords
    data: dict[str, Any] | None = None
    try:
        context = await browser.new_context(
            user_agent=_DISTRICT_USER_AGENT,
            geolocation={"latitude": lat, "longitude": lon},
            permissions=["geolocation"],
        )
        try:
            page = await context.new_page()

            loop = asyncio.get_event_loop()
            response_future: asyncio.Future = loop.create_future()

            async def on_response(resp: Any) -> None:
                if "get_discovery_results" in resp.url and not response_future.done():
                    try:
                        response_future.set_result(await resp.json())
                    except Exception as e:  # malformed body — report, don't crash
                        if not response_future.done():
                            response_future.set_exception(e)

            page.on("response", on_response)
            await page.goto(
                _DISTRICT_EVENTS_URL,
                wait_until="domcontentloaded",
                timeout=_DISTRICT_PAGE_TIMEOUT_MS,
            )
            data = await asyncio.wait_for(
                response_future, timeout=_DISTRICT_RESPONSE_TIMEOUT_S
            )
        finally:
            await context.close()
    except Exception as e:
        logger.warning("District.in scrape failed for %r: %s", city, type(e).__name__)
        return []

    return _parse_discovery_results(data or {}, fallback_city=city)


async def fetch_district_events(city: str) -> list[EventRecord]:
    """Single-city convenience wrapper: launches its own headless Chromium
    instance for just this one city, then delegates to
    `_fetch_one_city_with_browser`. Kept for callers that only need one
    city (and for the existing test suite); `ingest_india_events()` itself
    uses `fetch_district_events_batch` to amortize the browser-launch cost
    across many cities.

    Never raises: a missing Playwright install degrades to `[]`, the same
    best-effort contract as every fetcher in `scrapers/india_events.py`.
    """
    if city not in _DISTRICT_CITY_COORDS:
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.info("playwright not installed — skipping District.in scrape for %r", city)
        return []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            return await _fetch_one_city_with_browser(browser, city)
        finally:
            await browser.close()


async def fetch_district_events_batch(
    cities: list[str], max_concurrent: int = _DISTRICT_BATCH_CONCURRENCY
) -> dict[str, list[EventRecord]]:
    """Fetch District.in events for many cities using a single shared
    headless Chromium browser (one launch, one context per city) instead of
    launching a fresh browser per city — browser launch is the dominant
    per-city cost (several seconds), so amortizing it across `cities` cuts
    total runtime roughly proportionally to `len(cities)`, which matters
    once `ingest_india_events()` sweeps all 58 cities in
    `_INGEST_DEFAULT_CITIES` instead of 7. Concurrency within the shared
    browser is bounded by `max_concurrent` so District.in doesn't receive
    dozens of simultaneous navigations at once.

    Never raises: a missing Playwright install degrades every city to `[]`.
    A single city's failure (caught inside `_fetch_one_city_with_browser`)
    never affects any other city in the batch. Returns a dict keyed by city
    so callers can tell which cities actually yielded events.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.info(
            "playwright not installed — skipping District.in scrape for %d cities",
            len(cities),
        )
        return {city: [] for city in cities}

    results: dict[str, list[EventRecord]] = {}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _one(browser: Any, city: str) -> None:
        async with semaphore:
            results[city] = await _fetch_one_city_with_browser(browser, city)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                await asyncio.gather(*(_one(browser, city) for city in cities))
            finally:
                await browser.close()
    except Exception as e:
        # A browser-launch failure (e.g. resource contention, a corrupted
        # local Chromium cache — observed live 2026-10-06) must not take
        # down the rest of `ingest_india_events()`'s independent tiers: it
        # previously ran sequentially with its own try/except per call, but
        # since `ingest_india_events()` now runs this batch concurrently
        # with the HTTP-based tiers via `asyncio.gather`, an uncaught
        # exception here would propagate and cancel/discard the sibling
        # tier's already-gathered results too. Degrade every city in this
        # batch to `[]` instead, the same best-effort contract as every
        # other fetcher.
        logger.warning(
            "District.in batch scrape failed for %d cities: %s", len(cities), type(e).__name__
        )
        return {city: results.get(city, []) for city in cities}

    return results


def _parse_discovery_results(data: dict[str, Any], fallback_city: str) -> list[EventRecord]:
    """Walks every rail/item in a `get_discovery_results` response and maps
    each `EventData` block to an `EventRecord`. A malformed individual item
    is skipped (logged at debug), never drops the whole batch."""
    records: list[EventRecord] = []
    rails = (data.get("EDSResponse") or {}).get("rails") or []
    for rail in rails:
        for item in rail.get("items", []):
            event_data = (item.get("ItemDetails") or {}).get("EventData")
            if not event_data:
                continue
            record = _district_item_to_record(event_data, fallback_city)
            if record:
                records.append(record)
            if len(records) >= _DISTRICT_MAX_EVENTS_PER_CITY:
                return records
    return records


def _district_item_to_record(event_data: dict[str, Any], fallback_city: str) -> EventRecord | None:
    """Best-effort mapping from one District.in `EventData` item to an
    `EventRecord`. Returns None (rather than raising) for a malformed item."""
    try:
        start_epoch = event_data["start_time_epoch"]
        end_epoch = event_data.get("end_time_epoch") or start_epoch
        start = datetime.fromtimestamp(start_epoch, tz=_IST).date()
        end = datetime.fromtimestamp(end_epoch, tz=_IST).date()
        name = event_data["name"]
        slug = event_data.get("event_slug")
        tags_text = " ".join(t for t in event_data.get("tags", []) if t)

        return EventRecord(
            name=name,
            start_date=start,
            end_date=end,
            location=event_data.get("city") or fallback_city,
            interest_category=_guess_category(f"{name} {tags_text}"),
            source_citation="District.in (headless render)",
            deep_link=f"https://www.district.in/events/{slug}" if slug else None,
        )
    except (KeyError, ValueError, TypeError, ValidationError):
        logger.debug("Skipping malformed District.in item: %r", event_data.get("name"))
        return None
