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
_DISTRICT_CITY_COORDS: dict[str, tuple[float, float]] = {
    "Mumbai": (19.0760, 72.8777),
    "Delhi": (28.6139, 77.2090),
    "Bengaluru": (12.9716, 77.5946),
    "Hyderabad": (17.3850, 78.4867),
    "Chennai": (13.0827, 80.2707),
    "Kolkata": (22.5726, 88.3639),
    "Pune": (18.5204, 73.8567),
}

_DISTRICT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
_DISTRICT_EVENTS_URL = "https://www.district.in/events/"
_DISTRICT_PAGE_TIMEOUT_MS = 30_000
_DISTRICT_RESPONSE_TIMEOUT_S = 15.0
_DISTRICT_MAX_EVENTS_PER_CITY = 20


async def fetch_district_events(city: str) -> list[EventRecord]:
    """Launch a headless Chromium instance, resolve District.in's city
    context to `city` via injected browser geolocation, navigate to its
    events listing, and parse the structured event items out of the page's
    own `get_discovery_results` response.

    Never raises: a missing Playwright install, a navigation/timeout
    failure, or a malformed response all degrade to `[]`, the same
    best-effort contract as every fetcher in `scrapers/india_events.py`.
    Returns `[]` immediately for a city with no seed coordinate in
    `_DISTRICT_CITY_COORDS` (no reliable way to resolve its location
    context).
    """
    coords = _DISTRICT_CITY_COORDS.get(city)
    if coords is None:
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.info("playwright not installed — skipping District.in scrape for %r", city)
        return []

    lat, lon = coords
    data: dict[str, Any] | None = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                context = await browser.new_context(
                    user_agent=_DISTRICT_USER_AGENT,
                    geolocation={"latitude": lat, "longitude": lon},
                    permissions=["geolocation"],
                )
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
                await browser.close()
    except Exception as e:
        logger.warning("District.in scrape failed for %r: %s", city, type(e).__name__)
        return []

    return _parse_discovery_results(data or {}, fallback_city=city)


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
