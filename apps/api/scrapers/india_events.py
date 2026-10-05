"""Pan-India events ingester (docs/plans/india-workation-finder-plan.md).

Powers the India Workation & Long Weekend Finder's "what's happening around
India" layer — distinct from (and in addition to) the existing Epic 4
per-destination seasonal-narrative signals (Wikivoyage/Wikipedia/OSM/YouTube).
No single feed covers music + food + culture + pilgrimage + sports + craft
across the whole country, so this module layers three tiers, in priority
order, and merges/dedupes the result:

  - **Primary** — official, free-tier developer APIs (AllEvents.in,
    Eventbrite, Bandsintown). Each is a documented no-op (log + return `[]`)
    when its API key is unset, same contract as `scrapers/youtube_comments.py`'s
    `youtube_api_key` check — never raises for a missing key, and a transient
    HTTP failure degrades to `[]` rather than taking down the whole ingest.
  - **Tier A** — a small curated static dataset (`_CURATED_EVENTS` below) for
    major recurring pilgrimage/cultural festivals and sports-league windows
    the APIs above don't reliably cover. Refreshed periodically by hand, same
    pattern as `services/data/india_holidays.json` — see
    `docs/data-freshness-strategy.md`.
  - **Tier B** — a best-effort Wikipedia scrape fallback for gaps the above
    leave (regional food festivals, craft workshops not covered by a
    national tourism body). Walks public MediaWiki category pages — no API
    key/signup needed — and regex-parses a date range + location out of each
    member page's intro text; see `scrape_wikipedia_festivals()`'s docstring
    for specifics and its confidence/skip rules.

Every `EventRecord` carries a `source_citation` — never fabricate an event
without a traceable source, per the plan's provenance requirement (same
discipline as the existing hidden-gems feature).

Reddit is NOT a source here — retired product-wide 2026-07-26, see
docs/rag-strategy.md.
"""
from __future__ import annotations

import asyncio
import calendar
import hashlib
import logging
import re
import time
from datetime import date
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from core.config import settings
from core.embeddings import embed
from core.qdrant import get_qdrant

logger = logging.getLogger(__name__)

InterestCategory = Literal["music", "food", "culture", "pilgrimage", "sports", "craft"]

_MAX_FETCH_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 5.0


class EventRecord(BaseModel):
    """One pan-India event, from any tier. Shared return shape across every
    client function in this module so `ingest_india_events()` can merge/dedupe
    them uniformly regardless of source."""

    name: str
    start_date: date
    end_date: date
    location: str = Field(description="City/state, e.g. 'Pushkar, Rajasthan'")
    interest_category: InterestCategory
    source_citation: str = Field(description="e.g. 'AllEvents.in API' or a direct source URL")
    deep_link: str | None = None


# ---------------------------------------------------------------------------
# Primary tier — official free-tier developer APIs
# ---------------------------------------------------------------------------

async def fetch_allevents(city: str = "India", max_results: int = 50) -> list[EventRecord]:
    """Fetch upcoming events from the AllEvents.in API for `city`.

    Returns `[]` (never raises) when `settings.allevents_api_key` is unset or
    on any request failure, matching every other scraper's best-effort
    contract (e.g. `scrapers/youtube_comments.py`'s `youtube_api_key` guard).
    """
    if not settings.allevents_api_key:
        logger.info("ALLEVENTS_API_KEY not set — skipping AllEvents.in fetch for %r", city)
        return []

    params = {
        "key": settings.allevents_api_key,
        "location": city,
        "limit": max_results,
    }

    data: dict[str, Any] | None = None
    for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get("https://api.allevents.in/v1/events", params=params)
                if resp.status_code in (401, 403, 429):
                    logger.warning(
                        "AllEvents.in refused for %r (HTTP %d) — not retrying",
                        city, resp.status_code,
                    )
                    return []
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                if attempt == _MAX_FETCH_ATTEMPTS:
                    logger.warning(
                        "AllEvents.in fetch failed for %r after %d attempts: %s",
                        city, attempt, type(e).__name__,
                    )
                    return []
                await asyncio.sleep(_RETRY_BASE_DELAY_S * attempt)

    records: list[EventRecord] = []
    for item in (data or {}).get("data", []):
        record = _allevents_item_to_record(item)
        if record:
            records.append(record)
    return records


def _allevents_item_to_record(item: dict[str, Any]) -> EventRecord | None:
    """Best-effort mapping from one AllEvents.in API item to an EventRecord.
    Returns None (rather than raising) for a malformed item — a single bad
    record from a third-party API must not drop the whole batch."""
    try:
        return EventRecord(
            name=item["title"],
            start_date=item["start_time"][:10],
            end_date=(item.get("end_time") or item["start_time"])[:10],
            location=item.get("venue", {}).get("city") or item.get("city", "India"),
            interest_category=_guess_category(item.get("category", "")),
            source_citation="AllEvents.in API",
            deep_link=item.get("event_url"),
        )
    except Exception:
        logger.debug("Skipping malformed AllEvents.in item: %r", item)
        return None


async def fetch_eventbrite(city: str = "India", max_results: int = 50) -> list[EventRecord]:
    """Fetch upcoming events from the Eventbrite API for `city`.

    Returns `[]` (never raises) when `settings.eventbrite_api_key` is unset or
    on any request failure.
    """
    if not settings.eventbrite_api_key:
        logger.info("EVENTBRITE_API_KEY not set — skipping Eventbrite fetch for %r", city)
        return []

    headers = {"Authorization": f"Bearer {settings.eventbrite_api_key}"}
    params = {"location.address": city, "expand": "venue", "page_size": max_results}

    data: dict[str, Any] | None = None
    for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    "https://www.eventbriteapi.com/v3/events/search/",
                    params=params,
                    headers=headers,
                )
                if resp.status_code in (401, 403, 429):
                    logger.warning(
                        "Eventbrite refused for %r (HTTP %d) — not retrying",
                        city, resp.status_code,
                    )
                    return []
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                if attempt == _MAX_FETCH_ATTEMPTS:
                    logger.warning(
                        "Eventbrite fetch failed for %r after %d attempts: %s",
                        city, attempt, type(e).__name__,
                    )
                    return []
                await asyncio.sleep(_RETRY_BASE_DELAY_S * attempt)

    records: list[EventRecord] = []
    for item in (data or {}).get("events", []):
        record = _eventbrite_item_to_record(item)
        if record:
            records.append(record)
    return records


def _eventbrite_item_to_record(item: dict[str, Any]) -> EventRecord | None:
    """Best-effort mapping from one Eventbrite API item to an EventRecord."""
    try:
        venue = item.get("venue") or {}
        address = venue.get("address") or {}
        location = address.get("city") or address.get("region") or "India"
        return EventRecord(
            name=item["name"]["text"],
            start_date=item["start"]["local"][:10],
            end_date=item["end"]["local"][:10],
            location=location,
            interest_category=_guess_category(item.get("category_id", "")),
            source_citation="Eventbrite API",
            deep_link=item.get("url"),
        )
    except Exception:
        logger.debug("Skipping malformed Eventbrite item: %r", item)
        return None


async def fetch_bandsintown(artist: str) -> list[EventRecord]:
    """Fetch upcoming tour dates for `artist` from the Bandsintown Artist
    Events API, filtered to Indian venues. Bandsintown's API is per-artist
    (no city/country-wide search endpoint), so this supplements — rather than
    replaces — AllEvents.in/Eventbrite for the music category specifically;
    callers sweep a short list of popular touring artists.

    Returns `[]` (never raises) when `settings.bandsintown_app_id` is unset or
    on any request failure.
    """
    if not settings.bandsintown_app_id:
        logger.info("BANDSINTOWN_APP_ID not set — skipping Bandsintown fetch for %r", artist)
        return []

    params = {"app_id": settings.bandsintown_app_id}

    data: list[dict[str, Any]] | None = None
    for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    f"https://rest.bandsintown.com/artists/{artist}/events",
                    params=params,
                )
                if resp.status_code in (401, 403, 429):
                    logger.warning(
                        "Bandsintown refused for %r (HTTP %d) — not retrying",
                        artist, resp.status_code,
                    )
                    return []
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                if attempt == _MAX_FETCH_ATTEMPTS:
                    logger.warning(
                        "Bandsintown fetch failed for %r after %d attempts: %s",
                        artist, attempt, type(e).__name__,
                    )
                    return []
                await asyncio.sleep(_RETRY_BASE_DELAY_S * attempt)

    records: list[EventRecord] = []
    for item in data or []:
        record = _bandsintown_item_to_record(item)
        if record and "india" in (record.location or "").lower():
            records.append(record)
    return records


def _bandsintown_item_to_record(item: dict[str, Any]) -> EventRecord | None:
    """Best-effort mapping from one Bandsintown API item to an EventRecord."""
    try:
        venue = item.get("venue") or {}
        location = ", ".join(p for p in (venue.get("city"), venue.get("country")) if p) or "India"
        return EventRecord(
            name=venue.get("name") or item.get("title") or "Concert",
            start_date=item["datetime"][:10],
            end_date=item["datetime"][:10],
            location=location,
            interest_category="music",
            source_citation="Bandsintown API",
            deep_link=item.get("url"),
        )
    except Exception:
        logger.debug("Skipping malformed Bandsintown item: %r", item)
        return None


def _guess_category(raw_category: str) -> InterestCategory:
    """Best-effort mapping from a free-text/ID category string (API-specific
    vocabulary) onto the fixed `InterestCategory` set. Defaults to "culture"
    — the broadest, lowest-risk bucket — rather than raising, since a
    third-party API's category taxonomy will never line up exactly."""
    raw = (raw_category or "").lower()
    if any(k in raw for k in ("music", "concert", "gig")):
        return "music"
    if any(k in raw for k in ("food", "culinary", "drink")):
        return "food"
    if any(k in raw for k in ("pilgrim", "religious", "spiritual", "temple")):
        return "pilgrimage"
    if any(k in raw for k in ("sport", "match", "league", "marathon")):
        return "sports"
    if any(k in raw for k in ("craft", "handicraft", "art", "workshop")):
        return "craft"
    return "culture"


# ---------------------------------------------------------------------------
# Tier A — curated static dataset
# ---------------------------------------------------------------------------
#
# Hand-curated from Ministry of Tourism (incredibleindia.gov.in), ICCR/Sangeet
# Natak Akademi/NCPA public calendars, state tourism boards, and individual
# temple trust sites — see the plan's Tier A source list. A handful of
# well-known, high-confidence entries; NOT meant to be exhaustive. Refresh
# periodically (at least once a year, same cadence as
# `services/data/india_holidays.json`) rather than treating this as live data.
#
# Dates for lunar-calendar festivals (Durga Puja, Rath Yatra, etc.) shift
# year to year — these are illustrative/recent-year dates and must be
# re-verified against an official calendar before being surfaced for a new
# year; do not silently roll them forward.
#
# Refreshed 2026-10-04 against real sources (Drik Panchang lunar-calendar
# calculations, official tourism boards/league sites, reputable news
# reporting of announced schedules) — see the research trail in this
# session's history for full citation detail per entry. Two previously-listed
# recurring events are intentionally OMITTED this refresh rather than kept
# with guessed dates, per the "never fabricate" principle:
#   - Kumbh Mela: next edition confirmed for 2027 (Nashik-Trimbakeshwar) but
#     exact dates not yet publicly announced as of 2026-10-04.
#   - Pro Kabaddi League 2026-27: season not yet announced as of 2026-10-04
#     (last completed season was Aug-Dec 2025; no schedule exists yet).
# Re-add both once their real dates are officially announced.
#
# "Pan-India"/"Pan-India (multi-city)" location strings were replaced with a
# real representative host city for each entry — found during local testing
# to silently fail geocoding (and therefore get dropped from the destination
# shortlist entirely), since there's no single real place called "Pan-India".
_CURATED_EVENTS: list[dict[str, Any]] = [
    {
        "name": "Char Dham Yatra (opening)",
        "start_date": "2026-04-19",
        "end_date": "2026-04-23",
        "location": "Uttarakhand",
        "interest_category": "pilgrimage",
        "source_citation": "ANI/NDTV reporting of official opening dates (Gangotri & Yamunotri Apr 19, "
        "Kedarnath Apr 22, Badrinath Apr 23, 2026); registrationandtouristcare.uk.gov.in. "
        "Closing dates (~Diwali) not yet confirmed by official sources.",
    },
    {
        "name": "Rath Yatra (Puri)",
        "start_date": "2026-07-16",
        "end_date": "2026-07-16",
        "location": "Puri, Odisha",
        "interest_category": "pilgrimage",
        "source_citation": "Drik Panchang lunar-calendar calculation (Ashadha Shukla Dwitiya, 2026). "
        "2026 has an Adhik Maas leap month shifting this later than the typical late-June date — "
        "not yet independently corroborated by an Odisha Tourism/temple administration press release.",
    },
    {
        "name": "Durga Puja (Mahashtami-Vijayadashami)",
        "start_date": "2026-10-19",
        "end_date": "2026-10-21",
        "location": "Kolkata, West Bengal",
        "interest_category": "culture",
        "source_citation": "Drik Panchang lunar-calendar calculation (Mahashtami Oct 19, pan-India "
        "Vijayadashami Oct 20, Bengal-tradition Vijayadashami Oct 21, 2026).",
    },
    {
        "name": "Diwali (Lakshmi Puja)",
        "start_date": "2026-11-08",
        "end_date": "2026-11-08",
        "location": "New Delhi",
        "interest_category": "culture",
        "source_citation": "Drik Panchang Lakshmi Puja Muhurat calculation, 2026. Celebrated "
        "pan-India; New Delhi used as a real, geocodable representative anchor city.",
    },
    {
        "name": "Dev Deepawali",
        "start_date": "2026-11-24",
        "end_date": "2026-11-24",
        "location": "Varanasi, Uttar Pradesh",
        "interest_category": "culture",
        "source_citation": "Drik Panchang Kartik Purnima calculation, 2026 — Varanasi's ghats "
        "illuminated with lakhs of diyas, a well-known standalone travel draw distinct from Diwali itself.",
    },
    {
        "name": "Pushkar Mela",
        "start_date": "2026-11-20",
        "end_date": "2026-11-24",
        "location": "Pushkar, Rajasthan",
        "interest_category": "culture",
        "source_citation": "Drik Panchang Kartik Purnima/Pushkar Snana calculation (Mahasnana Nov 24, "
        "2026); the broader civic fair/trading-day window is set by the Ajmer district administration "
        "closer to the date and not yet separately confirmed.",
    },
    {
        "name": "Indian Premier League (IPL) 2026 season",
        "start_date": "2026-03-28",
        "end_date": "2026-05-31",
        "location": "Ahmedabad, Gujarat",
        "interest_category": "sports",
        "source_citation": "Wikipedia \"2026 Indian Premier League\" (citing ESPNcricinfo reporting). "
        "Season already concluded (final at Narendra Modi Stadium, Ahmedabad, May 31, 2026); multi-city "
        "league also played at Bengaluru, Dharamsala, Mullanpur and others. IPL 2027 window not yet announced.",
    },
    {
        "name": "Indian Super League (ISL) 2026-27 season",
        "start_date": "2026-10-10",
        "end_date": "2027-05-31",
        "location": "Kolkata, West Bengal",
        "interest_category": "sports",
        "source_citation": "ESPN.in, \"ISL 2026-27 season to begin on October 10\" (Sep 3, 2026); "
        "Wikipedia \"2026-27 Indian Super League\". 13-club multi-city league incl. Mumbai, Bengaluru, "
        "Chennai, Kochi, Goa, Bhubaneswar; Kolkata (East Bengal FC, Mohun Bagan Super Giant) used as anchor.",
    },
    {
        "name": "Vaishno Devi Yatra (Shardiya Navratri peak)",
        "start_date": "2026-10-11",
        "end_date": "2026-10-19",
        "location": "Katra, Jammu and Kashmir",
        "interest_category": "pilgrimage",
        "source_citation": "Kashmir Observer / Moneycontrol reporting of Shardiya Navratri pilgrim-rush "
        "dates, 2026; maavaishnodevi.org (official shrine board). Broader peak season runs March-October.",
    },
]



def curated_tier_a_events() -> list[EventRecord]:
    """Return the curated Tier A dataset as validated `EventRecord`s."""
    return [EventRecord(**entry) for entry in _CURATED_EVENTS]


# ---------------------------------------------------------------------------
# Tier B — Wikipedia scrape fallback (best-effort)
# ---------------------------------------------------------------------------
#
# Walks public MediaWiki category pages (no API key/signup needed, same
# "scrape a public wiki" shape as `scrapers/wikivoyage.py`/
# `scrapers/itinerary_corpus.py`) for gaps the API + curated tiers leave
# (regional food festivals, craft workshops, local sporting fixtures not
# covered by a national tourism body or a ticketing platform).
#
# `Category:Recurring sporting events established in India` (named in the
# original plan) does not actually exist on Wikipedia as of this writing —
# `Category:Annual sporting events in India` is the real equivalent and is
# used instead; `Category:Festivals in India` is real and used as-is.
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"

_WIKI_CATEGORIES: dict[str, InterestCategory | None] = {
    # None => classify via `_guess_category()` against the page's own text.
    "Category:Festivals in India": None,
    "Category:Annual sporting events in India": "sports",
}

# Caps so a runaway/huge category can't turn this into an unbounded crawl —
# "best-effort fallback", not "mirror all of Wikipedia".
_MAX_WIKI_CATEGORY_MEMBERS = 800
_MAX_WIKI_CATEGORY_PAGES = 4  # cmcontinue pages per category, at cmlimit=500 each
_WIKI_EXTRACTS_BATCH_SIZE = 50  # MediaWiki's per-request titles cap for non-bot accounts
_WIKI_REQUEST_DELAY_S = 0.3  # politeness gap between requests, same rationale as
# `scrapers/wikivoyage.py`'s `_DISTRICT_FETCH_DELAY_S` — this scraper's category walk
# + batched extracts fetch issues a burst of requests rather than one or two.

_MONTH_NAMES: dict[str, int] = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
# Longest-name-first so e.g. "September" doesn't get cut short by "Sep".
_MONTH_RE_PART = "|".join(sorted(_MONTH_NAMES.keys(), key=len, reverse=True))
_ORDINAL = r"(?:st|nd|rd|th)?"

# Ordered most-specific-first; each is tried in turn and the first match wins.
_RANGE_MONTH_DD_MONTH_DD_YEAR_RE = re.compile(
    rf"\b({_MONTH_RE_PART})\s+(\d{{1,2}}){_ORDINAL}\s*(?:to|[-\u2013\u2014])\s*"
    rf"({_MONTH_RE_PART})\s+(\d{{1,2}}){_ORDINAL},?\s+(\d{{4}})\b",
    re.IGNORECASE,
)
_RANGE_DD_DD_MONTH_YEAR_RE = re.compile(
    rf"\b(\d{{1,2}}){_ORDINAL}\s*(?:to|[-\u2013\u2014])\s*(\d{{1,2}}){_ORDINAL}\s+"
    rf"({_MONTH_RE_PART})\s+(\d{{4}})\b",
    re.IGNORECASE,
)
_SINGLE_MONTH_DD_YEAR_RE = re.compile(
    rf"\b({_MONTH_RE_PART})\s+(\d{{1,2}}){_ORDINAL},?\s+(\d{{4}})\b", re.IGNORECASE
)
_SINGLE_DD_MONTH_YEAR_RE = re.compile(
    rf"\b(\d{{1,2}}){_ORDINAL}\s+({_MONTH_RE_PART})\s+(\d{{4}})\b", re.IGNORECASE
)
_DD_MONTH_NO_YEAR_RE = re.compile(
    rf"\b(\d{{1,2}}){_ORDINAL}\s+day\s+of\s+({_MONTH_RE_PART})\b", re.IGNORECASE
)
# "celebrated/held on February 19"/"on the 19th of February" — plain
# day+month with no year at all. Only trusted when a recurrence keyword is
# also present elsewhere in the extract (see `has_recurrence` below), since
# on its own "on <date>" is also how a one-off historical fact reads.
_ON_MONTH_DD_NO_YEAR_RE = re.compile(
    rf"\bon\s+({_MONTH_RE_PART})\s+(\d{{1,2}}){_ORDINAL}\b", re.IGNORECASE
)
_ON_DD_MONTH_NO_YEAR_RE = re.compile(
    rf"\bon\s+(?:the\s+)?(\d{{1,2}}){_ORDINAL}(?:\s+of)?\s+({_MONTH_RE_PART})\b", re.IGNORECASE
)
_MONTH_RANGE_NO_YEAR_RE = re.compile(
    rf"\b({_MONTH_RE_PART})\s*[-\u2013\u2014]\s*({_MONTH_RE_PART})\b", re.IGNORECASE
)
_RECURRENCE_KEYWORDS_RE = re.compile(
    r"\b(annual(?:ly)?|every\s+year|each\s+year|traditionally\s+held)\b", re.IGNORECASE
)

# A year-bearing match is only trusted if it's recent/near-future — an
# extract mentioning a specific past edition ("the following edition was
# held on 15 January 2023") or a founding/birth year centuries ago ("the
# corresponding date as 19th Feb 1630") is real text but not a reliable
# signal of the event's *next* occurrence, which is what this scraper is
# surfacing events for. Out-of-window matches fall through to the
# no-year/month-only heuristics below rather than being used as-is.
_YEAR_LOOKBEHIND = 1
_YEAR_LOOKAHEAD = 2


def _plausible_year(year: int) -> bool:
    current_year = date.today().year
    return current_year - _YEAR_LOOKBEHIND <= year <= current_year + _YEAR_LOOKAHEAD


def _first_plausible_match(pattern: re.Pattern[str], text: str, year_group: int) -> re.Match[str] | None:
    """First regex match (in document order) whose year group passes
    `_plausible_year` — a pattern can match a stray historical date before a
    genuine recent/upcoming one later in the same extract."""
    for m in pattern.finditer(text):
        if _plausible_year(int(m.group(year_group))):
            return m
    return None

# Used only as a last-resort, lowest-confidence fallback (a single month
# mention plus a nearby recurrence keyword) — gated on "reasonable
# confidence": skipped entirely if more than one distinct month is named
# anywhere in the extract, since that's ambiguous rather than a clean signal.
_ANY_MONTH_RE = re.compile(rf"\b({_MONTH_RE_PART})\b", re.IGNORECASE)

# States/UTs + a working set of major festival/event host cities — used to
# recognize a genuinely Indian, geocodable location string in free text
# rather than ever inventing one. Not exhaustive; extend as gaps are found.
_INDIAN_STATES_AND_UTS = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands",
    "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
    "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]
_MAJOR_INDIAN_CITIES = [
    "Mumbai", "New Delhi", "Delhi", "Bengaluru", "Bangalore", "Hyderabad", "Chennai",
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Surat", "Lucknow", "Kanpur", "Nagpur",
    "Indore", "Bhopal", "Visakhapatnam", "Patna", "Vadodara", "Ludhiana", "Agra",
    "Nashik", "Varanasi", "Srinagar", "Amritsar", "Prayagraj", "Ranchi", "Jodhpur",
    "Coimbatore", "Guwahati", "Mysuru", "Mysore", "Thiruvananthapuram", "Kochi",
    "Madurai", "Puri", "Udaipur", "Pushkar", "Shillong", "Gangtok", "Leh", "Shimla",
    "Dehradun", "Panaji", "Bhubaneswar", "Raipur", "Jammu", "Kozhikode", "Thrissur",
    "Hampi", "Ajmer", "Bikaner", "Jaisalmer", "Nagaur", "Kullu", "Manali", "Haridwar",
    "Rishikesh", "Mathura", "Vrindavan", "Konark",
]


def _resolve_upcoming_year(month: int, day: int | None = None) -> int:
    """Pick the year that makes a recurring (year-less) annual event's next
    occurrence lie on or after today, so a month/day scraped from a generic
    "held every <month>"-style sentence lands on a forward-looking,
    realistic date rather than defaulting to a value that may already be
    months in the past."""
    today = date.today()
    if day is not None:
        try:
            candidate = date(today.year, month, day)
        except ValueError:
            candidate = date(today.year, month, 1)
        return today.year if candidate >= today else today.year + 1
    last_day = calendar.monthrange(today.year, month)[1]
    month_end = date(today.year, month, last_day)
    return today.year if month_end >= today else today.year + 1


def _parse_event_date_range(text: str) -> tuple[date, date] | None:
    """Best-effort date-range extraction from a Wikipedia intro extract.
    Tries progressively less specific patterns and returns the first
    confident, plausible match; returns `None` (caller skips the page)
    rather than guessing when nothing reliable is found — never fabricate
    a date.

    Year-bearing patterns require `_plausible_year` (recent/near-future) —
    an intro mentioning a past specific edition or a centuries-old founding
    date is real text but not a signal of the event's *next* occurrence, so
    those matches are passed over in favor of a later, plausible match (or
    a less specific, year-less heuristic) rather than used as-is."""
    if m := _first_plausible_match(_RANGE_MONTH_DD_MONTH_DD_YEAR_RE, text, 5):
        month1, day1, month2, day2, year = m.groups()
        year = int(year)
        return (
            date(year, _MONTH_NAMES[month1.lower()], int(day1)),
            date(year, _MONTH_NAMES[month2.lower()], int(day2)),
        )
    if m := _first_plausible_match(_RANGE_DD_DD_MONTH_YEAR_RE, text, 4):
        day1, day2, month, year = m.groups()
        year = int(year)
        month_num = _MONTH_NAMES[month.lower()]
        return date(year, month_num, int(day1)), date(year, month_num, int(day2))
    if m := _first_plausible_match(_SINGLE_MONTH_DD_YEAR_RE, text, 3):
        month, day, year = m.groups()
        d = date(int(year), _MONTH_NAMES[month.lower()], int(day))
        return d, d
    if m := _first_plausible_match(_SINGLE_DD_MONTH_YEAR_RE, text, 3):
        day, month, year = m.groups()
        d = date(int(year), _MONTH_NAMES[month.lower()], int(day))
        return d, d

    # Everything below is year-less, so only trusted alongside an explicit
    # recurrence cue ("annual", "every year", ...) elsewhere in the extract
    # — without one, a bare day+month mention is just as likely to be an
    # incidental historical fact as the event's actual recurring date.
    has_recurrence = bool(_RECURRENCE_KEYWORDS_RE.search(text))
    if has_recurrence:
        if m := _DD_MONTH_NO_YEAR_RE.search(text):
            day, month = m.groups()
            month_num = _MONTH_NAMES[month.lower()]
            year = _resolve_upcoming_year(month_num, int(day))
            d = date(year, month_num, int(day))
            return d, d
        if m := _ON_MONTH_DD_NO_YEAR_RE.search(text):
            month, day = m.groups()
            month_num = _MONTH_NAMES[month.lower()]
            year = _resolve_upcoming_year(month_num, int(day))
            d = date(year, month_num, int(day))
            return d, d
        if m := _ON_DD_MONTH_NO_YEAR_RE.search(text):
            day, month = m.groups()
            month_num = _MONTH_NAMES[month.lower()]
            year = _resolve_upcoming_year(month_num, int(day))
            d = date(year, month_num, int(day))
            return d, d

    if m := _MONTH_RANGE_NO_YEAR_RE.search(text):
        month1, month2 = m.groups()
        m1, m2 = _MONTH_NAMES[month1.lower()], _MONTH_NAMES[month2.lower()]
        year = _resolve_upcoming_year(m1)
        last_day2 = calendar.monthrange(year, m2)[1]
        return date(year, m1, 1), date(year, m2, last_day2)

    if has_recurrence:
        months_found = {mn.lower() for mn in _ANY_MONTH_RE.findall(text)}
        if len(months_found) == 1:
            month_num = _MONTH_NAMES[next(iter(months_found))]
            year = _resolve_upcoming_year(month_num)
            last_day = calendar.monthrange(year, month_num)[1]
            return date(year, month_num, 1), date(year, month_num, last_day)
    return None


def _parse_event_location(text: str) -> str | None:
    """Best-effort location extraction, constrained to a known list of real
    Indian states/UTs and major cities so the result is a realistically
    geocodable "City, State"/"City, India"/state-name string (per
    `services/geocode.py`'s free-text city lookup) — never a vague or
    invented placeholder."""
    state_alternation = "|".join(re.escape(s) for s in _INDIAN_STATES_AND_UTS)
    city_state_re = re.compile(
        rf"\b([A-Z][A-Za-z.']+(?:\s+[A-Z][A-Za-z.']+){{0,2}}),\s*({state_alternation}|India)\b"
    )
    if m := city_state_re.search(text):
        return f"{m.group(1).strip()}, {m.group(2).strip()}"
    for city in _MAJOR_INDIAN_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", text):
            return city
    for state in _INDIAN_STATES_AND_UTS:
        if re.search(rf"\b{re.escape(state)}\b", text):
            return state
    return None


def _fetch_wiki_category_members(client: httpx.Client, cmtitle: str) -> list[str]:
    """Page titles in a Wikipedia category, via `list=categorymembers`,
    paginating through `cmcontinue` up to `_MAX_WIKI_CATEGORY_PAGES` pages
    (capped at `_MAX_WIKI_CATEGORY_MEMBERS` titles total). `cmnamespace=0`
    restricts to articles — excludes subcategory/talk entries that would
    otherwise pollute the member list."""
    titles: list[str] = []
    cmcontinue: str | None = None
    for _ in range(_MAX_WIKI_CATEGORY_PAGES):
        params: dict[str, Any] = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": cmtitle,
            "cmlimit": 500,
            "cmnamespace": 0,
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        try:
            resp = client.get(WIKIPEDIA_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("Wikipedia categorymembers fetch failed for %r: %s", cmtitle, type(e).__name__)
            break
        titles.extend(
            m["title"] for m in data.get("query", {}).get("categorymembers", []) if "title" in m
        )
        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue or len(titles) >= _MAX_WIKI_CATEGORY_MEMBERS:
            break
        time.sleep(_WIKI_REQUEST_DELAY_S)
    return titles[:_MAX_WIKI_CATEGORY_MEMBERS]


def _fetch_wiki_extracts(client: httpx.Client, titles: list[str]) -> dict[str, str]:
    """Plain-text intro extracts for a batch of page titles, via
    `prop=extracts&exintro=1&explaintext=1`, batched at
    `_WIKI_EXTRACTS_BATCH_SIZE` titles per request (MediaWiki's own cap for
    non-bot accounts) to minimize request count. A single bad/slow batch is
    caught and skipped rather than aborting the whole scrape — same
    per-request isolation as every other tier's per-page error handling."""
    extracts: dict[str, str] = {}
    for i in range(0, len(titles), _WIKI_EXTRACTS_BATCH_SIZE):
        batch = titles[i : i + _WIKI_EXTRACTS_BATCH_SIZE]
        params = {
            "action": "query",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "redirects": 1,
            "titles": "|".join(batch),
            "format": "json",
        }
        try:
            resp = client.get(WIKIPEDIA_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(
                "Wikipedia extracts fetch failed for a batch of %d titles: %s",
                len(batch), type(e).__name__,
            )
            continue
        for page in data.get("query", {}).get("pages", {}).values():
            title = page.get("title")
            if title:
                extracts[title] = page.get("extract", "")
        if i + _WIKI_EXTRACTS_BATCH_SIZE < len(titles):
            time.sleep(_WIKI_REQUEST_DELAY_S)
    return extracts


def scrape_wikipedia_festivals() -> list[EventRecord]:
    """Lowest-confidence fallback tier for gaps the API + curated tiers leave
    (regional food festivals, craft workshops, local sporting fixtures not
    covered by a national tourism body or a ticketing platform).

    Walks `Category:Festivals in India` and `Category:Annual sporting
    events in India` via the public, keyless MediaWiki API
    (`action=query&list=categorymembers`), fetches each member page's intro
    text (`action=query&prop=extracts&exintro=1&explaintext=1`, batched),
    and regex-parses a date range + an Indian state/city location out of
    that text.

    No single Wikipedia infobox schema exists across arbitrary festival/
    sporting-event pages the way an API response has one, so this is
    deliberately conservative: a page whose intro doesn't yield a
    reasonably confident date range *and* a recognized Indian location is
    skipped entirely rather than emitting a record with a guessed or
    partial value — same "never fabricate, cite real sources" discipline as
    every other tier in this module (`source_citation` is always the real
    Wikipedia page URL). Best-effort throughout: a network failure on one
    category or one batch of extracts degrades to skipping just that chunk,
    never raises, and the function still returns whatever it could parse.
    """
    headers = {"User-Agent": settings.nominatim_user_agent}
    title_category: dict[str, InterestCategory | None] = {}

    try:
        with httpx.Client(timeout=15, headers=headers) as client:
            for cmtitle, forced_category in _WIKI_CATEGORIES.items():
                if len(title_category) >= _MAX_WIKI_CATEGORY_MEMBERS:
                    break
                for title in _fetch_wiki_category_members(client, cmtitle):
                    title_category.setdefault(title, forced_category)
                    if len(title_category) >= _MAX_WIKI_CATEGORY_MEMBERS:
                        break
                time.sleep(_WIKI_REQUEST_DELAY_S)

            extracts = _fetch_wiki_extracts(client, list(title_category.keys()))
    except Exception as e:
        logger.warning("Wikipedia Tier B category walk failed entirely: %s", type(e).__name__)
        return []

    records: list[EventRecord] = []
    parsed_count = 0
    skipped_count = 0
    for title, extract in extracts.items():
        if not extract:
            skipped_count += 1
            continue
        date_range = _parse_event_date_range(extract)
        location = _parse_event_location(extract)
        if date_range is None or location is None:
            skipped_count += 1
            continue
        start, end = date_range
        forced_category = title_category.get(title)
        category = forced_category or _guess_category(f"{title} {extract[:300]}")
        page_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
        try:
            records.append(
                EventRecord(
                    name=title,
                    start_date=start,
                    end_date=end,
                    location=location,
                    interest_category=category,
                    source_citation=page_url,
                    deep_link=page_url,
                )
            )
            parsed_count += 1
        except Exception:
            logger.debug("Skipping malformed Wikipedia-derived event for %r", title)
            skipped_count += 1

    logger.debug(
        "Wikipedia Tier B scrape: %d parsed, %d skipped (of %d candidate pages)",
        parsed_count, skipped_count, len(extracts),
    )
    return records


# ---------------------------------------------------------------------------
# Orchestration — merge + dedupe across tiers
# ---------------------------------------------------------------------------

def _dedupe_key(record: EventRecord) -> tuple[str, str, str, str]:
    """Identity for dedup purposes: same name + same date range + same
    location is the same event, regardless of which tier/source reported it.
    Case/whitespace-insensitive so trivial formatting differences between
    sources (e.g. "Pushkar Mela" vs "pushkar mela ") don't produce
    duplicates."""
    return (
        record.name.strip().lower(),
        record.start_date.isoformat(),
        record.end_date.isoformat(),
        record.location.strip().lower(),
    )


async def ingest_india_events(cities: list[str] | None = None) -> list[EventRecord]:
    """Top-level orchestration: fetch every tier, merge, and dedupe by
    (name, start_date, end_date, location). Best-effort throughout — a
    missing API key or a failed fetch from one tier never blocks the others,
    consistent with every client function's own no-op contract above.

    `cities` defaults to a short list of major metros for the primary-tier
    city-scoped API sweeps; callers doing a broader batch ingest (the
    scheduler job another workstream wires up) can pass a longer list.
    """
    if cities is None:
        cities = ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Pune"]

    all_records: list[EventRecord] = []

    for city in cities:
        all_records.extend(await fetch_allevents(city))
        all_records.extend(await fetch_eventbrite(city))

    all_records.extend(curated_tier_a_events())
    all_records.extend(scrape_wikipedia_festivals())

    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[EventRecord] = []
    for record in all_records:
        key = _dedupe_key(record)
        if key not in seen:
            seen.add(key)
            deduped.append(record)

    return deduped


# ---------------------------------------------------------------------------
# Embedding + Qdrant ingestion
# ---------------------------------------------------------------------------

def _event_text(record: EventRecord) -> str:
    """Text embedded for semantic retrieval — interest + location + name, the
    same shape a query embedding (interest + date-window + location, per the
    plan's retrieval design) is built from."""
    return (
        f"{record.name} ({record.interest_category}) in {record.location}, "
        f"{record.start_date.isoformat()} to {record.end_date.isoformat()}"
    )


def embed_and_store_india_events(events: list[EventRecord]) -> int:
    """Embed each `EventRecord` and upsert into the `india_events` Qdrant
    collection. Mirrors `scrapers/osm.py`/`scrapers/youtube_comments.py`'s
    embed-then-upsert pattern: point IDs are a stable hash of the dedup key,
    so re-running this is safe — it updates in place rather than
    duplicating. Returns the number of points written."""
    if not events:
        return 0

    from qdrant_client.models import PointStruct

    texts = [_event_text(e) for e in events]
    vectors = embed(texts)

    points = []
    for event, vec in zip(events, vectors):
        point_id = hashlib.md5("::".join(_dedupe_key(event)).encode()).hexdigest()
        point_id_int = int(point_id, 16) % (2**63)
        payload = {
            "name": event.name,
            "start_date": event.start_date.isoformat(),
            "end_date": event.end_date.isoformat(),
            "location": event.location,
            "interest_category": event.interest_category,
            "source_citation": event.source_citation,
            "deep_link": event.deep_link,
            "text": texts[len(points)],
        }
        points.append(PointStruct(id=point_id_int, vector=vec, payload=payload))

    client = get_qdrant()
    client.upsert(collection_name=settings.qdrant_collection_india_events, points=points)
    return len(points)
