"""Workation destination recommendation chain (docs/plans/india-workation-finder-plan.md).

Ties together the three modules prior workstreams already built — never
reimplements their logic, only orchestrates them:

- `services/long_weekend.py::get_long_weekends` — deterministic long-weekend
  windows for the traveller's home state.
- `scrapers/india_events.py` — the `india_events` Qdrant collection, already
  batch-embedded by the scheduler job described in the plan. This chain
  retrieves from it *semantically* (interest + date-window + location as the
  query embedding), the same "corpus supplies breadth cheaply" pattern the
  plan calls out, rather than calling `ingest_india_events()` live.
- `services/workation_venues.py::find_workation_venues` — wifi-verified venue
  shortlist per candidate destination.
- `services/geocode.py::geocode_city` — lat/lon for every destination and
  event location, required so the frontend's India map visualization has a
  point to plot. Per the plan's hard requirement, a destination or event that
  fails to geocode is dropped rather than shipped with null/placeholder
  coordinates — but one bad geocode never drops the whole response.

Mirrors `chains/recommend_cities_chain.py`'s house style: Pydantic request/
response models, an LLM-assisted rationale pass via `core/llm_client.py`, and
a `_mock_response`/`_mock_rationale`-style deterministic fallback whenever the
LLM is unavailable or fails — this chain must never crash or fabricate a
destination with no supporting data (per the plan's provenance discipline,
same as hidden-gems and the events feed itself).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date

from pydantic import BaseModel

from core.config import settings
from core.embeddings import embed
from core.llm_client import track_gemini_usage
from core.prompt_guard import neutralize
from core.qdrant import get_qdrant
from services.geocode import geocode_city
from services.long_weekend import LongWeekendWindow, get_long_weekends
from services.workation_venues import WorkationVenueResult, find_workation_venues

logger = logging.getLogger(__name__)

# How many of the best-ranked long-weekend windows to actually search events
# for. Searching every window in a year would be wasteful (and most of the
# value — per the plan's "top-ranked window" framing — is in the next good
# one), so only the best few are considered.
_TOP_WINDOWS_CONSIDERED = 2

# Semantic search breadth/quality knobs for the india_events collection.
# Pan-India breadth means casting a fairly wide net (_EVENT_SEARCH_LIMIT) and
# then filtering in Python by date-window overlap and interest match, since
# `location` isn't a payload-indexed field here (see core/qdrant.py's
# `_DESTINATION_INDEXED_COLLECTIONS` comment — india_events is deliberately
# excluded from it, events are pan-India, not keyed by a single destination).
_EVENT_SEARCH_LIMIT = 40
_MIN_EVENT_SCORE = 0.20

# Candidate destination shortlist size — matches the plan's "3-5 candidate
# destinations" framing.
_MIN_DESTINATIONS = 3
_MAX_DESTINATIONS = 5
_MAX_EVENTS_PER_DESTINATION = 3

# Hard per-destination deadline for the venue-signal enrichment pass. Venue
# data is a nice-to-have ("workation-friendly wifi spots") on top of the core
# events/long-weekend result, so it must never be allowed to make the whole
# `/recommend` request fail or stall — see `_find_workation_venues_bounded`.
_VENUE_LOOKUP_DEADLINE_S = 20.0


class WorkationRecommendRequest(BaseModel):
    # `state` is optional per the "Leave Planner" redesign's second discovery
    # mode: a traveller who doesn't want to anchor to a home state's gazetted
    # holiday calendar at all, and just wants to browse what's happening
    # across India for a specific weekend/date range they already have in
    # mind. That mode requires `date_range` instead (validated in
    # `recommend_workation`) since there's no state to derive a window from.
    state: str | None = None
    interests: list[str]
    date_range: tuple[str, str] | None = None


class EventSummary(BaseModel):
    """Simplified event summary, enriched with lat/lon for the map view."""

    name: str
    start_date: str
    end_date: str
    location: str
    lat: float
    lon: float
    interest_category: str
    source_citation: str
    deep_link: str | None = None


class VenueSummary(BaseModel):
    """Derived from `WorkationVenueResult` — just the counts/flag a card
    needs, not the full venue list (the handoff/detail view can call
    `find_workation_venues` again if it needs the full shortlist)."""

    total_venues_found: int
    venues_with_verified_wifi_count: int
    has_limited_coverage: bool


class DestinationCandidate(BaseModel):
    destination: str
    lat: float
    lon: float
    rationale: str
    matching_events: list[EventSummary]
    venue_summary: VenueSummary
    workation_split: str


class LongWeekendSummary(BaseModel):
    """Trimmed view of `LongWeekendWindow` for the response — field names kept
    identical so the frontend doesn't need two shapes for "the same thing"."""

    start_date: str
    end_date: str
    total_days_off: int
    leave_days_needed: int
    reason: str
    value: float


class WorkationRecommendResponse(BaseModel):
    long_weekends: list[LongWeekendSummary]
    destinations: list[DestinationCandidate]
    has_results: bool
    message: str = ""


_RATIONALE_PROMPT = """\
You are a travel expert helping an Indian remote worker plan a short workation \
around an upcoming long weekend.

Long weekend: {window_desc}
Traveller's interests: {interests}

For each candidate destination below, write ONE short (1-2 sentence) rationale \
explaining why it fits the traveller's interests, referencing the specific \
event(s) happening there during this window where possible.

Candidate destinations and their matching events:
{destinations_block}

Respond ONLY with a JSON object mapping destination name -> rationale string \
(no markdown, no explanation):
{{"Destination Name": "rationale text", ...}}
"""


async def recommend_workation(request: WorkationRecommendRequest) -> WorkationRecommendResponse:
    """Top-level orchestration for `POST /api/workation/recommend` (router is a
    separate workstream — this is the function it imports).

    Never fabricates: a state with no long weekends, or a long weekend with no
    matching events/geocodable destinations, returns `has_results=False` with
    an explanatory `message` rather than an invented destination.

    Two discovery modes, matching the Leave Planner UI's two entry points:
    - `request.state` set: anchor to that state's gazetted long-weekend
      calendar (original behaviour, unchanged) — optionally narrowed to one
      specific window via `request.date_range` once the user has picked it.
    - `request.state` omitted: "just show me events across India for a
      weekend I already have in mind" — skips `get_long_weekends()` (there's
      no state to compute a holiday calendar for) and builds a single
      synthetic window directly from the required `request.date_range`
      instead, via `_window_from_date_range()`.
    """
    if request.state:
        windows = get_long_weekends(request.state)

        if not windows:
            return WorkationRecommendResponse(
                long_weekends=[],
                destinations=[],
                has_results=False,
                message=f"No upcoming long weekends found for {request.state}.",
            )

        if request.date_range is not None:
            windows = _filter_windows_by_date_range(windows, request.date_range)
            if not windows:
                return WorkationRecommendResponse(
                    long_weekends=[],
                    destinations=[],
                    has_results=False,
                    message=(
                        f"No long weekend for {request.state} overlaps "
                        f"{request.date_range[0]} to {request.date_range[1]}."
                    ),
                )
    else:
        if request.date_range is None:
            return WorkationRecommendResponse(
                long_weekends=[],
                destinations=[],
                has_results=False,
                message="Pick a home state, or a specific weekend/date range to browse events for.",
            )
        window = _window_from_date_range(request.date_range)
        if window is None:
            return WorkationRecommendResponse(
                long_weekends=[],
                destinations=[],
                has_results=False,
                message=f"Couldn't understand the date range {request.date_range[0]} to {request.date_range[1]}.",
            )
        windows = [window]

    long_weekend_summaries = [_window_to_summary(w) for w in windows]

    geocode_cache: dict[str, tuple[float, float] | None] = {}
    events_by_destination: dict[str, list[dict]] = {}

    for window in windows[:_TOP_WINDOWS_CONSIDERED]:
        hits = await _retrieve_matching_events(window, request.interests)
        for hit in hits:
            city = _city_from_location(hit["location"])
            if not city:
                continue
            events_by_destination.setdefault(city, []).append(hit)

    if not events_by_destination:
        return WorkationRecommendResponse(
            long_weekends=long_weekend_summaries,
            destinations=[],
            has_results=False,
            message="No events matching your interests were found around your upcoming long weekends.",
        )

    top_window = windows[0]
    destinations: list[DestinationCandidate] = []

    # Cities ranked by how many matching events they have, most first.
    ranked_cities = sorted(events_by_destination.items(), key=lambda kv: -len(kv[1]))

    # First pass: geocoding + event summaries only (cheap, cached, no
    # external network dependency beyond the geocoder). Venue lookups are
    # deliberately deferred to a second, concurrent pass below rather than
    # being awaited inline here — see `_find_workation_venues_bounded`'s
    # docstring for why.
    candidates: list[tuple[str, tuple[float, float], list[EventSummary]]] = []
    for city, raw_events in ranked_cities:
        if len(candidates) >= _MAX_DESTINATIONS:
            break

        # Geocode using the first event's full "City, State" location rather
        # than the bare city name: common Indian city names (e.g. "Katra")
        # are ambiguous globally without state context and can silently
        # resolve to a same-named place on the other side of the world.
        # Prefer an event's own precise lat/lon (AllEvents.in's JSON-LD
        # tier supplies these) over this ambiguous city-name geocode when
        # available.
        dest_coords = _event_payload_coords(raw_events[0])
        if dest_coords is None:
            dest_coords = await _geocode_cached(raw_events[0]["location"], geocode_cache)
        if dest_coords is None:
            dest_coords = await _geocode_cached(city, geocode_cache)
        if dest_coords is None:
            continue  # per the plan's hard requirement: drop, don't null-island it

        event_summaries: list[EventSummary] = []
        for raw in raw_events[:_MAX_EVENTS_PER_DESTINATION]:
            event_coords = (
                _event_payload_coords(raw)
                or await _geocode_cached(raw["location"], geocode_cache)
                or dest_coords
            )
            event_summaries.append(
                EventSummary(
                    name=raw["name"],
                    start_date=raw["start_date"],
                    end_date=raw["end_date"],
                    location=raw["location"],
                    lat=event_coords[0],
                    lon=event_coords[1],
                    interest_category=raw["interest_category"],
                    source_citation=raw["source_citation"],
                    deep_link=raw.get("deep_link"),
                )
            )

        candidates.append((city, dest_coords, event_summaries))

    # Second pass: fetch venue signal for all candidate cities *concurrently*
    # rather than one-at-a-time, each bounded by an overall deadline. Before
    # this fix, a live production incident showed Overpass connection
    # failures compounding in series (several destinations x several retries
    # each) into multi-minute total latency, well past the frontend's
    # request timeout, so `/recommend` failed outright for the whole request
    # even though venue data is a nice-to-have enrichment, not the core
    # result. `find_workation_venues` already degrades gracefully to an
    # empty/limited-coverage result on its own failures; `asyncio.wait_for`
    # here adds a hard ceiling so even an unexpected hang can't do the same
    # thing to the response as a whole.
    venue_results = await asyncio.gather(
        *(_find_workation_venues_bounded(city) for city, _, _ in candidates)
    )

    for (city, dest_coords, event_summaries), venue_result in zip(candidates, venue_results):
        venue_summary = VenueSummary(
            total_venues_found=venue_result.total_venues_found,
            venues_with_verified_wifi_count=venue_result.venues_with_verified_wifi_count,
            has_limited_coverage=venue_result.has_limited_coverage,
        )

        destinations.append(
            DestinationCandidate(
                destination=city,
                lat=dest_coords[0],
                lon=dest_coords[1],
                rationale="",  # filled in below
                matching_events=event_summaries,
                venue_summary=venue_summary,
                workation_split=_workation_split(top_window),
            )
        )

    if not destinations:
        return WorkationRecommendResponse(
            long_weekends=long_weekend_summaries,
            destinations=[],
            has_results=False,
            message="Found matching events, but none of their locations could be mapped — try again later.",
        )

    destinations = await _fill_rationales(destinations, top_window, request.interests)

    return WorkationRecommendResponse(
        long_weekends=long_weekend_summaries,
        destinations=destinations,
        has_results=True,
    )


def _window_to_summary(window: LongWeekendWindow) -> LongWeekendSummary:
    return LongWeekendSummary(
        start_date=window.start_date.isoformat(),
        end_date=window.end_date.isoformat(),
        total_days_off=window.total_days_off,
        leave_days_needed=window.leave_days_needed,
        reason=window.reason,
        value=window.value,
    )


def _workation_split(window: LongWeekendWindow) -> str:
    """"5 WFH days (Mon-Fri) + Sat-Sun exploring"-style text, computed from
    the window's total_days_off: the rest of a standard 7-day week is spent
    working remotely from the destination, the days off are for exploring."""
    explore_days = max(window.total_days_off, 1)
    wfh_days = max(7 - explore_days, 0)
    if wfh_days == 0:
        return f"{explore_days} days exploring ({window.reason})"
    return f"{wfh_days} WFH days + {explore_days} days exploring ({window.reason})"


def _city_from_location(location: str) -> str:
    """`EventRecord.location` is documented as 'City/state, e.g. "Pushkar,
    Rajasthan"' — take the city part for deduping/display."""
    return location.split(",")[0].strip()


def _event_payload_coords(raw: dict) -> tuple[float, float] | None:
    """An event's own precise coordinates, when its source supplied them
    (e.g. AllEvents.in's JSON-LD `geo` block) — bypasses the ambiguous
    city-name geocode entirely for these, since a specific venue's lat/lon
    is strictly more accurate than re-deriving it from a city string."""
    lat, lon = raw.get("lat"), raw.get("lon")
    if lat is not None and lon is not None:
        return (lat, lon)
    return None


async def _geocode_cached(
    place: str, cache: dict[str, tuple[float, float] | None]
) -> tuple[float, float] | None:
    """`geocode_city` memoized per-request so the same city/location string
    (an event's location, repeated across several matching events, or a
    destination city derived from several of them) is only looked up once."""
    if place in cache:
        return cache[place]
    try:
        geo = await geocode_city(place)
        result: tuple[float, float] | None = (geo.lat, geo.lon)
    except Exception as e:
        logger.info("Geocode failed for %r, dropping from map results: %s", place, e)
        result = None
    cache[place] = result
    return result


async def _find_workation_venues_bounded(city: str) -> WorkationVenueResult:
    """`find_workation_venues` wrapped with a hard wall-clock deadline.

    `find_workation_venues` already degrades gracefully on its own (Overpass
    failures resolve to an empty, `has_limited_coverage=True` result rather
    than raising) — but a 2026-10-06 production incident showed Railway's
    cloud IP range getting hard connection failures from both configured
    Overpass mirrors, and the venue lookups for several destinations running
    *in series* inside the caller's loop meant those per-destination retry
    budgets stacked into several minutes of total latency, well past the
    frontend's request timeout, failing `/recommend` outright. Venue data is
    an enrichment on top of the core events/long-weekend result, not the
    result itself, so it must never be allowed to do that. This adds a
    second, independent safety net: if a single destination's lookup somehow
    still runs long, it's abandoned at `_VENUE_LOOKUP_DEADLINE_S` and treated
    the same honest way `find_workation_venues` treats a real Overpass
    failure — zero venues, flagged as limited coverage — rather than ever
    blocking the response.
    """
    try:
        return await asyncio.wait_for(
            find_workation_venues(city), timeout=_VENUE_LOOKUP_DEADLINE_S
        )
    except TimeoutError:
        logger.warning(
            "Venue lookup for %r exceeded %.0fs deadline, degrading to limited coverage",
            city, _VENUE_LOOKUP_DEADLINE_S,
        )
        return WorkationVenueResult(
            venues=[],
            total_venues_found=0,
            venues_with_verified_wifi_count=0,
            has_limited_coverage=True,
        )


async def _retrieve_matching_events(
    window: LongWeekendWindow, interests: list[str]
) -> list[dict]:
    """Semantic retrieval against the pre-embedded `india_events` Qdrant
    collection, mirroring `services/visa.py::retrieve_visa_note`'s retrieval
    pattern (embed a query, search, score-floor the hits) applied to a
    different collection. Interest-category and date-window relevance are
    then enforced in Python, since this collection has no payload index to
    filter on (see module docstring).

    Never raises: a retrieval failure degrades to `[]`, same contract as
    `retrieve_visa_note` — one bad Qdrant call must not break the whole
    recommendation.
    """
    interests_text = ", ".join(interests) if interests else "music food culture pilgrimage sports craft"
    query_text = (
        f"{interests_text} events in India between {window.start_date.isoformat()} "
        f"and {window.end_date.isoformat()}"
    )

    try:
        vector = (await asyncio.to_thread(embed, [query_text]))[0]
        client = get_qdrant()
        hits = await asyncio.to_thread(
            lambda: client.search(
                collection_name=settings.qdrant_collection_india_events,
                query_vector=vector,
                limit=_EVENT_SEARCH_LIMIT,
                with_payload=True,
            )
        )
    except Exception as e:
        logger.warning("india_events retrieval failed for window %s: %s", window.start_date, e)
        return []

    interests_lower = {i.strip().lower() for i in interests}
    matches: list[dict] = []
    for hit in hits:
        if hit.score < _MIN_EVENT_SCORE:
            continue
        payload = hit.payload or {}
        if not payload.get("name") or not payload.get("location"):
            continue
        if interests_lower and payload.get("interest_category", "").lower() not in interests_lower:
            continue
        if not _overlaps_window(payload, window):
            continue
        matches.append(payload)

    return matches


def _overlaps_window(payload: dict, window: LongWeekendWindow) -> bool:
    try:
        event_start = date.fromisoformat(payload["start_date"])
        event_end = date.fromisoformat(payload["end_date"])
    except (KeyError, ValueError):
        return False
    return event_start <= window.end_date and event_end >= window.start_date


def _filter_windows_by_date_range(
    windows: list[LongWeekendWindow], date_range: tuple[str, str]
) -> list[LongWeekendWindow]:
    """Restricts candidate long-weekend windows to ones overlapping the
    caller-supplied `date_range`, preserving the existing value-based
    ranking order. Invalid/unparseable date strings fail closed (empty
    result, which the caller turns into an honest "nothing found" message)
    rather than silently ignoring the caller's explicit date constraint."""
    try:
        range_start = date.fromisoformat(date_range[0])
        range_end = date.fromisoformat(date_range[1])
    except (ValueError, IndexError, TypeError):
        return []
    return [w for w in windows if w.start_date <= range_end and w.end_date >= range_start]


def _window_from_date_range(date_range: tuple[str, str]) -> LongWeekendWindow | None:
    """Builds a single synthetic `LongWeekendWindow` directly from an explicit
    date range the user picked themselves — the Leave Planner's "just browse
    events across India for a weekend I already have in mind" mode, which has
    no home state and therefore nothing for `get_long_weekends()` to compute
    a gazetted-holiday window from. `reason`/`leave_days_needed` are honest
    placeholders (there's no holiday being reasoned about here, just the
    traveller's own chosen dates) rather than fabricated holiday context.

    Returns `None` for an unparseable or inverted (`end < start`) range so the
    caller can fail closed with an explanatory message, same contract as
    `_filter_windows_by_date_range`.
    """
    try:
        start = date.fromisoformat(date_range[0])
        end = date.fromisoformat(date_range[1])
    except (ValueError, IndexError, TypeError):
        return None
    if end < start:
        return None
    total_days = (end - start).days + 1
    return LongWeekendWindow(
        start_date=start,
        end_date=end,
        total_days_off=total_days,
        leave_days_needed=0,
        reason="Selected dates",
        value=float(total_days),
    )


async def _fill_rationales(
    destinations: list[DestinationCandidate],
    window: LongWeekendWindow,
    interests: list[str],
) -> list[DestinationCandidate]:
    """LLM-assisted rationale pass, mirroring `recommend_cities_chain`'s mock
    fallback: any missing API key/import/network failure degrades to a
    deterministic templated rationale rather than crashing or blocking the
    response."""
    if settings.llm_provider == "mock":
        return _mock_rationales(destinations, interests)

    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        logger.warning("google-genai not installed, using mock rationales")
        return _mock_rationales(destinations, interests)

    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set, using mock rationales")
        return _mock_rationales(destinations, interests)

    window_desc = f"{window.start_date.isoformat()} to {window.end_date.isoformat()} ({window.reason})"
    destinations_block = "\n".join(
        f"- {d.destination}: " + "; ".join(e.name for e in d.matching_events)
        for d in destinations
    )

    prompt = _RATIONALE_PROMPT.format(
        window_desc=neutralize(window_desc, context="long weekend window"),
        interests=neutralize(", ".join(interests) or "general travel", context="interests"),
        destinations_block=neutralize(destinations_block, context="destinations block"),
    )

    client = google_genai.Client(api_key=settings.gemini_api_key)

    def _call_sync():
        return client.models.generate_content(
            model=settings.gemini_model,
            contents=[genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])],
            config=genai_types.GenerateContentConfig(temperature=0.4, max_output_tokens=512),
        )

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _call_sync)
        track_gemini_usage(response, model=settings.gemini_model, purpose="workation_recommend")
        raw = response.text
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        rationale_by_destination = json.loads(cleaned)
        for d in destinations:
            d.rationale = rationale_by_destination.get(d.destination) or _mock_rationale(d, interests)
        return destinations
    except Exception as e:
        logger.warning("Gemini API failed for workation rationale: %s: %s", type(e).__name__, e)
        return _mock_rationales(destinations, interests)


def _mock_rationales(
    destinations: list[DestinationCandidate], interests: list[str]
) -> list[DestinationCandidate]:
    for d in destinations:
        d.rationale = _mock_rationale(d, interests)
    return destinations


def _mock_rationale(destination: DestinationCandidate, interests: list[str]) -> str:
    if destination.matching_events:
        names = ", ".join(e.name for e in destination.matching_events[:2])
        return f"{destination.destination} has {names} coming up during this window."
    interests_text = ", ".join(interests) if interests else "a relaxed workation"
    return f"{destination.destination} is a solid match for {interests_text}."
