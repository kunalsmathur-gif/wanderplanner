from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any

from chains.safety import apply_kid_safety_filter, inject_persona_modules
from chains.scoring import calculate_alignment_score
from core import timing
from core.budget_tiers import budget_tier_prompt_hint
from core.config import settings
from core.cost_grounding import accommodation_cost_grounding_hint, flight_cost_grounding_hint
from core.llm_client import track_gemini_usage
from core.prompt_guard import neutralize, wrap_untrusted
from core.validation import MAX_TRIP_DAYS
from models.itinerary import (
    ExpenseBreakdown,
    ItineraryDay,
    ItineraryItem,
    ItineraryItemLocation,
    ItineraryResponse,
)
from models.trip import TripConfig
from services.itinerary_cache import get_cached_itinerary, store_itinerary
from services.rag_fallback import rag_skeleton_itinerary
from services.search import retrieve_context, retrieve_itinerary_examples, summarise_context
from services.visa import ensure_entry_info, entry_cost_grounding

logger = logging.getLogger(__name__)


async def _budget_guidance_block(trip_config: TripConfig) -> str:
    """Assemble the persona/purpose budget-tier hint + free-tools cost
    grounding (flight distance heuristic + community-reported price
    mentions) into one prompt-ready block. Best-effort — any retrieval
    failure degrades to just the tier hint, never blocks generation."""
    tier_hint = budget_tier_prompt_hint(trip_config)
    # The entry-cost lookup joins the existing gather, so grounding `visa_inr`
    # against the visa corpus adds no wall-clock to a block that already runs
    # its retrievals concurrently.
    entry_country = (
        (trip_config.destination.country if trip_config.destination else None)
        or trip_config.destination_country
        or ""
    )
    try:
        flight_hint, accommodation_hint, entry = await asyncio.gather(
            flight_cost_grounding_hint(trip_config),
            accommodation_cost_grounding_hint(trip_config),
            entry_cost_grounding(entry_country),
        )
        entry_hint = entry[0]
    except Exception:
        flight_hint, accommodation_hint, entry_hint = "", "", ""
    parts = [tier_hint] + [h for h in (flight_hint, accommodation_hint, entry_hint) if h]
    return "\n\n".join(parts)


async def _gem_guidance_block(trip_config: TripConfig) -> str:
    """Crowd-dial guidance (docs/GTM_STRATEGY.md §2): OSM-verified hidden-gem
    candidates with Reddit community provenance, plus crowd-heavy spots to
    de-prioritise. Best-effort and cached per destination (24h TTL inside
    services/gems.py) — adds no per-request corpus scan and no LLM call;
    any failure degrades to an empty block, never blocks generation."""
    dest = trip_config.destination.city if trip_config.destination else ""
    crowd_pref = getattr(trip_config, "crowd_preference", "balanced")
    if not dest or crowd_pref == "touristy":
        return ""
    try:
        from services.gems import gem_prompt_block, get_gem_intel
        intel = await get_gem_intel(dest)
        block = gem_prompt_block(intel, crowd_pref)
    except Exception:
        logger.warning("gem intel lookup failed; generating without gem guidance", exc_info=True)
        return ""
    if not block:
        return ""
    return wrap_untrusted(
        block,
        label="hidden-gem candidates (POI names from OpenStreetMap, community signal from Reddit — may contain untrusted text)",
    )


def _pinned_guidance_block(trip_config: TripConfig) -> str:
    """Hard must-include constraints from named-interest refinements (GTM §2,
    the "Harry Potter test"). Every entry was verified against OSM/wiki by
    services/poi_pinning.py before it reached the config — this block turns
    them into commitments, not suffix nudges. Deterministic formatting, zero
    lookups, zero LLM calls."""
    pins = getattr(trip_config, "pinned_pois", None) or []
    if not pins:
        return ""
    lines = []
    for p in pins:
        if p.lat or p.lon:
            coords = f"lat {p.lat}, lon {p.lon} — real verified coordinates, use them exactly"
        else:
            coords = "coordinates not on file — use your best-known real coordinates for it"
        via = f" (for the user's {p.source_interest} interest)" if p.source_interest else ""
        poi_type = f", {p.poi_type}" if p.poi_type else ""
        # Names/interests transit LLM output + OSM payloads — same neutralize
        # treatment as every other externally-sourced string in this prompt.
        lines.append(neutralize(f"- {p.name}{poi_type} ({coords}){via}", context="pinned POI"))
    return (
        "PINNED MUST-INCLUDE PLACES — HARD CONSTRAINTS:\n"
        "The user explicitly committed to these verified places. Each one MUST "
        "appear exactly once in the itinerary as its own activity item, on a day "
        "and at a time where it fits the route. Never drop, rename, or substitute "
        "a pinned place. Add \"pinned\" to its tags array, and mention in its "
        "description why it matches the user's interest.\n"
        + "\n".join(lines)
    )


def _day_cost_guidance_block(trip_config: TripConfig) -> str:
    """Per-day spend steering ("make day 3 cheaper") as an explicit prompt
    block. Deterministic formatting, zero lookups, zero LLM calls.

    The wording asks for a *relative* shift against the trip's other days
    rather than an absolute rupee target: we cannot know a defensible target
    for an arbitrary day, and naming one would invite the model to invent
    prices to hit it — the exact guessing this codebase avoids elsewhere. It
    also says explicitly not to drop a pinned place to save money, because
    that is the one way a cheaper day could silently break a hard constraint.
    """
    prefs = getattr(trip_config, "day_cost_preferences", None) or []
    if not prefs:
        return ""
    lines = []
    for pref in prefs:
        if pref.direction == "cheaper":
            lines.append(
                f"- Day {pref.day_number}: spend NOTICEABLY LESS than the other days. "
                "Prefer free or low-cost activities (parks, beaches, markets, walks, "
                "free-entry sites), street food or casual local eateries over "
                "restaurants, and public transport or walking over private taxis."
            )
        else:
            lines.append(
                f"- Day {pref.day_number}: this is the day to SPEND MORE. A signature "
                "experience, a notable restaurant, or a premium tour is appropriate here."
            )
    return (
        "PER-DAY SPEND PREFERENCES — the user asked for these explicitly:\n"
        + "\n".join(lines)
        + "\nReflect this in `estimated_cost_inr` on that day's items, and keep the "
        "day genuinely worthwhile — cheaper means better value, not an empty day. "
        "NEVER drop or move a pinned must-include place to make a day cheaper; "
        "pinned places stay exactly where the hard constraints above require."
    )


def _enforce_pins(days: list[ItineraryDay], trip_config: TripConfig) -> list[ItineraryDay]:
    """Deterministic hard-constraint enforcement (GTM §2): the prompt asks for
    each pinned place exactly once with the "pinned" tag, but LLM compliance
    is probabilistic (live 2026-07-13 eval: Barcelona honoured 1 of 3 pins —
    renamed/untagged the rest). Make the contract structural instead: match
    generated item titles against pins with the same fuzzy matcher used at
    verification time, tag the first match, untag duplicates, and inject any
    pin the LLM dropped. Pure CPU, zero LLM calls, bounded by MAX_PINNED_POIS."""
    pins = getattr(trip_config, "pinned_pois", None) or []
    if not pins or not days:
        return days
    from services.poi_pinning import _names_match, _normalize

    for pin in pins:
        pin_norm = _normalize(pin.name)
        if not pin_norm:
            continue
        matches = [
            item for day in days for item in day.items
            if _names_match(_normalize(item.title or ""), pin_norm)
        ]
        if matches:
            if "pinned" not in matches[0].tags:
                matches[0].tags = [*matches[0].tags, "pinned"]
            for extra in matches[1:]:
                if "pinned" in extra.tags:
                    extra.tags = [t for t in extra.tags if t != "pinned"]
        else:
            # Same shape as the _mock_itinerary injection: an evening slot on
            # the lightest day, real verified coordinates when we have them.
            day = min(days, key=lambda d: len(d.items))
            day.items.append(ItineraryItem(
                id=str(uuid.uuid4()),
                time_start="19:00",
                time_end="21:00",
                title=pin.name,
                description=(
                    f"Pinned for your {pin.source_interest or 'special'} "
                    "interest — a verified real place."
                ),
                location=ItineraryItemLocation(lat=pin.lat, lon=pin.lon, address=""),
                tags=["experience", "pinned"],
            ))
    return days


async def _flag_unverified_items(
    days: list[ItineraryDay], trip_config: TripConfig
) -> list[ItineraryDay]:
    """Mark items whose title doesn't correspond to anything in our ingested
    OSM/wiki corpus for the destination as unverified (GTM follow-up to
    _enforce_pins): the system prompt only forbids inventing a *hidden_gem*
    tag not on the verified candidate list — nothing stops the model from
    including an ordinary, untagged item it recalled from training data
    rather than the retrieved research. Pinned items are always verified by
    construction (_enforce_pins only tags/injects real, coordinate-bearing
    places) so they're skipped here rather than re-checked."""
    dest = trip_config.destination.city if trip_config.destination else ""
    if not dest:
        return days
    titles = [
        item.title for day in days for item in day.items
        if "pinned" not in item.tags and (item.title or "").strip()
    ]
    if not titles:
        return days
    from services.poi_pinning import verify_item_titles

    verified_titles = await verify_item_titles(titles, dest)
    for day in days:
        for item in day.items:
            if "pinned" in item.tags:
                continue
            item.verified = (item.title or "") in verified_titles
    return days


# Generous enough to cover a legitimate long day-trip within the same
# country/region (e.g. Edinburgh → Isle of Skye is ~400km one-way, still
# Scotland; Paris → Versailles or Bali's own Nusa Penida hop are much
# shorter), but tight enough to catch the actual failure mode observed live:
# the model naming a landmark from a totally different country/continent
# than the trip (e.g. "Warner Bros Studio Tour, London" — several thousand
# km — suggested for a Bali itinerary). This is a coarse geographic sanity
# check, not a country-border lookup: we don't reverse-geocode item
# coordinates, so a same-country distance this size and a wrong-country jump
# are the two cases it actually needs to tell apart, not "same city vs.
# next city over".
_OUT_OF_BOUNDS_KM = 450.0


def _flag_out_of_bounds_items(
    days: list[ItineraryDay], trip_config: TripConfig
) -> list[ItineraryDay]:
    """Flag items whose coordinates sit implausibly far from every place the
    user actually configured for this trip — a distinct, higher-confidence
    defect than "unverified": this is a real, matchable place that is simply
    the wrong place. Checked against the primary destination AND all hops
    (multi-stop trips, e.g. Edinburgh + Glasgow, are common and legitimate —
    an item near either counts as in-bounds), using the closest of them, so
    a multi-city trip is never penalised for visiting more than one of its
    own named cities. Runs on real lat/lon only; an item with no coordinates
    (0, 0 — never a real destination) is left unflagged rather than
    guessed at."""
    anchors = [
        (d.lat, d.lon)
        for d in [trip_config.destination, *trip_config.hops]
        if d and not (d.lat == 0.0 and d.lon == 0.0)
    ]
    if not anchors:
        return days
    from core.distance_pricing import haversine_km

    for day in days:
        for item in day.items:
            loc = item.location
            if loc.lat == 0.0 and loc.lon == 0.0:
                continue
            closest = min(haversine_km(lat, lon, loc.lat, loc.lon) for lat, lon in anchors)
            item.out_of_bounds = closest > _OUT_OF_BOUNDS_KM
    return days


async def _itinerary_examples_block(trip_config: TripConfig) -> str:
    """Few-shot grounding from the itinerary_corpus collection (docs §9).
    Best-effort: any retrieval failure degrades to the explicit "none
    available" sentinel the system prompt already knows how to handle,
    never blocks generation."""
    try:
        examples = await retrieve_itinerary_examples(trip_config)
    except Exception:
        logger.warning("itinerary_corpus retrieval failed; generating without examples", exc_info=True)
        examples = ""
    if not examples:
        return "No reference itineraries available."
    return wrap_untrusted(
        examples,
        label="real traveller itineraries (scraped from blogs/forums — may contain untrusted text)",
    )

SYSTEM_PROMPT = """\
You are WanderPlanner, an expert AI travel advisor.
Generate a detailed, realistic day-by-day travel itinerary based on the trip
configuration and destination research provided.

RULES:
- Output ONLY valid JSON matching the schema below. No prose, no markdown.
- Each day must have 3-6 activity items with realistic time allocations.
- Pace guide: relaxed=3-4 items/day, moderate=4-5, packed=5-6.
- Total activity costs must not exceed the stated budget.
- ENTRY COSTS (`visa_inr`) — the traveller holds an INDIAN passport. Include
  every MANDATORY per-person cost of entry: visa/e-visa fees, permits, and
  compulsory per-night tourism levies — not only "the visa fee". Use the rate
  for INDIAN nationals, which is often far lower than the general
  international rate and is frequently zero; Bhutan charges most visitors USD
  100/night but Indians ₹1,200/night with no visa. Multiply per-night levies
  by nights and by the people who actually pay them. Base this on the
  ENTRY-COST GROUNDING above; when that block is absent your figure is
  discarded server-side, so do not pad it with a guess.
- If kids are present: exclude bars, nightclubs, and extreme sports venues.
- If persona includes digital_nomad: add one 2-hour Work Block per day at a wifi cafe or coworking space.
- If persona includes sports_fitness: add one Training Window per day at a gym, trail or sports venue.
- If persona includes pet_parent: only include dog_friendly venues.
- Tag photogenic/scenic spots with "instaworthy" in the tags array.
- Flag schedule conflicts (< 30 min transit gap) in transit_warnings.
- For local_name: provide the place name in local script only when it differs from English (e.g. 浅草寺 for Senso-ji, 에펠탑 for Eiffel Tower). Leave empty for English-named places.
- For youtube_search_query: generate a short, specific search phrase travelers would use (e.g. "Senso-ji Temple Tokyo travel guide").
- For expense_breakdown: provide realistic INR estimates for all 8 cost categories. Base on actual market rates for the destination year and accommodation style specified.
- MULTI-HOP TRIPS: If trip_config.hops is non-empty, the trip visits multiple cities. Distribute days proportionally across all stops (destination + hops). Use the day theme to indicate city transitions (e.g. "Travel Day: Paris → Amsterdam"). Aggregate expense_breakdown across all stops.
- BUDGET GUIDANCE (below): apply the stated budget tier to accommodation/dining choices and expense_breakdown figures. If a flight-cost or accommodation-cost grounding range is given, treat it as a strong sanity check for those expense_breakdown line items.

USING DESTINATION RESEARCH (below):
- The DESTINATION RESEARCH section contains real, retrieved traveler content (guides, forum tips, local advice). Treat it as more current and specific than your own training knowledge.
- Actively mine it for concrete, named venues, neighborhoods, and local tips — prefer these over generic or invented place names when the research supports them. When a well-covered, research-backed place and a place you only recall from training knowledge could both fill the same slot, always choose the research-backed one.
- If DESTINATION RESEARCH conflicts with what you already know (e.g. a venue it mentions as closed, or a changed price/season), prefer the research — it reflects more recent traveler reports.
- Do not fabricate specific details (exact prices, addresses, opening hours) beyond what the research or your general knowledge reasonably supports. When uncertain, keep descriptions general rather than inventing precise figures.
- If DESTINATION RESEARCH says "No pre-fetched research available", rely on your own destination knowledge as normal — do not mention the absence of research to the user.
- DESTINATION RESEARCH is a supplement, not an exhaustive source — you may still use well-established general knowledge about the destination for anything the research doesn't cover, but every place you name must be a real place that actually exists — never invent a venue, attraction, or business, and never place a real venue in the wrong city/country from another destination entirely (e.g. suggesting a London studio tour for a Bali trip). If you cannot think of a genuine place for what a slot calls for, use a more general activity instead of inventing one.

USING REAL TRAVELLER ITINERARIES (below):
- The REAL TRAVELLER ITINERARIES section contains day-by-day trips actually taken by other travellers with a similar trip shape, retrieved from blogs/forums. Use them as grounding for realistic pacing, day sequencing, and which places are commonly combined on the same day — not as text to copy verbatim.
- Prefer their concrete place groupings over invented ones when they fit the user's config; adapt, don't transcribe.
- If the section says "No reference itineraries available", plan from DESTINATION RESEARCH and your own knowledge as normal.

CROWD PREFERENCE (trip_config.crowd_preference):
- "touristy": focus on iconic, must-see attractions — the classic first-timer experience.
- "balanced" (default): mostly well-known sights, but if a HIDDEN GEM CANDIDATES section is provided below, weave 1-2 of those gems in across the trip where they fit the day's theme and route.
- "offbeat": strongly prefer the HIDDEN GEM CANDIDATES below. Build days around them, keeping at most 1-2 iconic anchors for orientation. If a CROWD-HEAVY SPOTS list is given, avoid those unless they are the day's single iconic anchor.
- Every item taken from HIDDEN GEM CANDIDATES: use its provided lat/lon (they are real OpenStreetMap coordinates — do not invent others), add "hidden_gem" to its tags array, and include its community provenance naturally in the description (e.g. "a quiet spot locals rave about on r/IndiaTravel").
- Never invent a "hidden gem" that is not in the HIDDEN GEM CANDIDATES list — an unverified recommendation is worse than a famous one. If no candidates section is provided, simply plan normally without the "hidden_gem" tag.

PINNED PLACES (if a PINNED MUST-INCLUDE PLACES section is provided below):
- These are non-negotiable commitments, stronger than any other guidance in this prompt: every pinned place must appear exactly once as its own itinerary item with the "pinned" tag.
- If a pinned place conflicts with pace limits, prefer dropping an unpinned filler activity over dropping the pin.

OUTPUT SCHEMA:
{{
  "days": [
    {{
      "day_number": 1,
      "date": "YYYY-MM-DD",
      "theme": "string",
      "items": [
        {{
          "id": "unique_string",
          "time_start": "HH:MM",
          "time_end": "HH:MM",
          "title": "string",
          "local_name": "place name in local script e.g. 浅草寺 (leave empty if same script as English)",
          "description": "string",
          "location": {{"lat": 0.0, "lon": 0.0, "address": "string"}},
          "tags": ["string"],
          "estimated_cost_inr": <what this ONE item costs the WHOLE GROUP in INR: entry/ticket price, the meal, or the ride. 0 if genuinely free (a beach, a walk, a temple with no entry fee). EXCLUDE flights and accommodation — those are trip-level, not a day's cost>,
          "booking_url": "string",
          "youtube_video_id": "",
          "youtube_search_query": "short search phrase for YouTube e.g. Senso-ji Temple Tokyo travel guide"
        }}
      ],
      "transit_warnings": []
    }}
  ],
  "expense_breakdown": {{
    "flights_inr": <round-trip economy flights, all passengers>,
    "visa_inr": <total MANDATORY entry cost all passengers — see ENTRY COSTS rule — 0 if none>,
    "accommodation_inr": <nightly rate INR × nights × rooms>,
    "activities_inr": <estimated total entry fees across all days>,
    "food_inr": <food cost per person per day × days × people>,
    "local_transport_inr": <metro/taxi/bus for all days × people>,
    "shopping_inr": <reasonable souvenir budget for destination>,
    "emergency_buffer_inr": <10% of sum of all above>,
    "total_inr": <sum of all above including buffer>,
    "destination_currency_code": "<3-letter ISO currency code e.g. JPY>",
    "total_destination_currency": <total_inr converted to destination currency approximately>,
    "num_people": <total group size>
  }}
}}

DESTINATION RESEARCH:
{context}

REAL TRAVELLER ITINERARIES FOR REFERENCE (use as inspiration, not verbatim):
{itinerary_examples}

{gem_guidance}

{pinned_guidance}

{day_cost_guidance}

{budget_guidance}

TRIP CONFIGURATION:
{trip_config}
"""


def _build_llm():
    if settings.llm_provider == "mock":
        return None  # handled in generate_itinerary
    if settings.llm_provider == "groq":
        try:
            from langchain_groq import ChatGroq
        except ImportError:
            raise RuntimeError("langchain-groq not installed. Run: pip install -r requirements-ml.txt")
        return ChatGroq(
            api_key=settings.groq_api_key,
            model="llama-3.1-70b-versatile",
            temperature=0.4,
        )
    if settings.llm_provider == "ollama":
        try:
            from langchain_community.llms import Ollama
        except ImportError:
            raise RuntimeError("langchain-community not installed. Run: pip install -r requirements-ml.txt")
        return Ollama(base_url=settings.ollama_base_url, model=settings.ollama_model)
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def _mock_itinerary(trip_config: TripConfig, tip_texts: list[str] | None = None) -> dict:
    """Return a canned itinerary for local dev without an LLM.

    `tip_texts` (Tier 3 fallback enhancement, docs §4): when the RAG-skeleton
    fallback (Tier 2) also can't build a plan (no OSM POIs ingested for this
    destination yet), we still splice in real retrieved wiki/reddit snippets
    where available, so the mock reads less like a generic placeholder.
    """
    dest = trip_config.destination.city if trip_config.destination else "the destination"
    dates = trip_config.dates if isinstance(trip_config.dates, dict) else {}
    start = dates.get("start_date") or dates.get("start") or "2026-11-14"
    from datetime import date, timedelta
    try:
        base = date.fromisoformat(start)
    except Exception:
        base = date(2026, 11, 14)
    num_days = 3
    end_raw = dates.get("end_date") or dates.get("end")
    if start and end_raw:
        try:
            # Clamped: this loop builds one dict per day with three items each,
            # so an unbounded span is a memory-exhaustion vector reachable from
            # a single request body. TripConfig now caps the start/end window
            # (core/validation.py), but this path also runs on dicts that never
            # went through that validator — eval harnesses, cached configs, and
            # the `isinstance(..., dict)` fallback just above.
            num_days = max(1, min(MAX_TRIP_DAYS, (date.fromisoformat(end_raw) - base).days))
        except Exception:
            pass

    tips = tip_texts or []

    def _with_tip(description: str, idx: int) -> str:
        if not tips:
            return description
        return f"{description} Local tip: {tips[idx % len(tips)]}"

    days: list[dict[str, Any]] = []
    themes = ["Arrival & City Highlights", "Culture & Food", "Day Trip & Leisure"]
    for i in range(num_days):
        day_date = (base + timedelta(days=i)).isoformat()
        theme = themes[i % len(themes)]
        days.append({
            "day_number": i + 1,
            "date": day_date,
            "theme": theme,
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "time_start": "09:00",
                    "time_end": "11:00",
                    "title": f"Morning Walk — {dest} Old Town",
                    "description": _with_tip(f"Explore the historic centre of {dest} on foot. Great for orientation and photos.", i * 3),
                    "location": {"lat": 0.0, "lon": 0.0, "address": f"Old Town, {dest}"},
                    "tags": ["instaworthy"],
                    "local_name": "",
                    "booking_url": "",
                    "youtube_video_id": "",
                    "youtube_search_query": "",
                },
                {
                    "id": str(uuid.uuid4()),
                    "time_start": "12:00",
                    "time_end": "13:30",
                    "title": "Local Lunch",
                    "description": _with_tip(f"Try the local cuisine at a well-rated restaurant near {dest} centre.", i * 3 + 1),
                    "location": {"lat": 0.0, "lon": 0.0, "address": f"City Centre, {dest}"},
                    "tags": ["kid_friendly"],
                    "local_name": "",
                    "booking_url": "",
                    "youtube_video_id": "",
                    "youtube_search_query": "",
                },
                {
                    "id": str(uuid.uuid4()),
                    "time_start": "15:00",
                    "time_end": "18:00",
                    "title": f"{dest} Main Museum",
                    "description": _with_tip(f"The top cultural attraction in {dest}. Book tickets online to skip queues.", i * 3 + 2),
                    "location": {"lat": 0.0, "lon": 0.0, "address": f"Museum District, {dest}"},
                    "tags": ["kid_friendly", "instaworthy"],
                    "local_name": "",
                    "booking_url": "",
                    "youtube_video_id": "",
                    "youtube_search_query": "",
                },
            ],
            "transit_warnings": [],
        })

    # Honour pinned must-include places in mock mode too (one per day, round-
    # robin) so the refine → pin → regenerate → diff loop is exercisable
    # without a live LLM.
    for idx, pin in enumerate(getattr(trip_config, "pinned_pois", None) or []):
        day = days[idx % len(days)]
        day["items"].append({
            "id": str(uuid.uuid4()),
            "time_start": "19:00",
            "time_end": "21:00",
            "title": pin.name,
            "description": f"Pinned for your {pin.source_interest or 'special'} interest — a verified real place.",
            "location": {"lat": pin.lat, "lon": pin.lon, "address": f"{dest}"},
            # tags[0] renders as the category badge; "pinned" in the rest
            # of the list renders the 📌 chip (see ItineraryTimeline.tsx).
            "tags": ["experience", "pinned"],
            "local_name": "",
            "booking_url": "",
            "youtube_video_id": "",
            "youtube_search_query": "",
        })
    return {
        "days": days,
        "expense_breakdown": {
            "flights_inr": 35000 * max(1, num_days // 3),
            "visa_inr": 6500,
            "accommodation_inr": 4500 * num_days,
            "activities_inr": 2000 * num_days,
            "food_inr": 1800 * num_days,
            "local_transport_inr": 800 * num_days,
            "shopping_inr": 3000,
            "emergency_buffer_inr": 0,
            "total_inr": 0,
            "destination_currency_code": "",
            "total_destination_currency": 0,
            "num_people": 2,
        },
    }


def _parse_expense_breakdown(
    raw: dict, trip_config: TripConfig, *, entry_grounded: bool = False
) -> ExpenseBreakdown:
    group = trip_config.group
    if hasattr(group, 'adults'):
        people = group.adults + group.seniors + len(group.kids if group.kids else [])
    else:
        g = group if isinstance(group, dict) else vars(group)
        people = g.get('adults', 1) + g.get('seniors', 0) + len(g.get('kids', []))
    people = max(people, 1)

    flights = int(raw.get("flights_inr", 0))
    # 🔴 A visa figure is allowed through ONLY when the corpus actually covered
    # this country — `entry_grounded` is the result of a real lookup, not the
    # model's opinion of its own confidence.
    #
    # Ungrounded, the number came from parametric memory: Bhutan produced
    # ₹41,000 for a 5-day trip, which is the international Sustainable
    # Development Fee (USD 100/night) in INR, for a traveller who needs no visa
    # and pays ₹1,200/night. Wrong rate, wrong label, indistinguishable from a
    # real figure once it is an int.
    #
    # None, not 0, when ungrounded — "we could not look this up" and "entry is
    # free" are different claims and the UI renders them differently. A prompt
    # rule cannot enforce this: an LLM has no calibrated sense of when it is
    # guessing, so the gate has to be structural.
    visa = int(raw.get("visa_inr", 0)) if entry_grounded else None
    accommodation = int(raw.get("accommodation_inr", 0))
    activities = int(raw.get("activities_inr", 0))
    food = int(raw.get("food_inr", 0))
    local_transport = int(raw.get("local_transport_inr", 0))
    shopping = int(raw.get("shopping_inr", 0))
    # An unknown entry cost contributes nothing to the total — the alternative
    # is inventing a placeholder, which is the bug this gate exists to stop.
    # ⚠️ The total therefore UNDERSTATES a trip with a real but unlooked-up
    # entry cost; the "not available" label is what stops that reading as free.
    subtotal = (
        flights + (visa or 0) + accommodation + activities + food + local_transport + shopping
    )
    buffer = int(raw.get("emergency_buffer_inr", round(subtotal * 0.10)))
    total = int(raw.get("total_inr", subtotal + buffer)) or (subtotal + buffer)

    return ExpenseBreakdown(
        flights_inr=flights,
        visa_inr=visa,
        accommodation_inr=accommodation,
        activities_inr=activities,
        food_inr=food,
        local_transport_inr=local_transport,
        shopping_inr=shopping,
        emergency_buffer_inr=buffer,
        total_inr=total,
        destination_currency_code=raw.get("destination_currency_code", ""),
        total_destination_currency=int(raw.get("total_destination_currency", 0)),
        num_people=people,
    )


def _classify_gemini_error(err_str: str) -> str:
    """Route a Gemini call failure: "transient" (retry same model with
    backoff), "model_missing" (retired/renamed model id — skip straight to
    the next fallback model), or "fatal" (auth/invalid request — raise)."""
    if any(kw in err_str for kw in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "quota")):
        return "transient"
    if "404" in err_str or "NOT_FOUND" in err_str or "is not found" in err_str:
        return "model_missing"
    return "fatal"


async def _gemini_itinerary(trip_config: TripConfig, cost_correction: str = "") -> dict:
    """Call Google Gemini directly with automatic retry on 503 errors."""
    import asyncio
    try:
        # NOTE: do not import from google.api_core here — that's a separate
        # package google-genai doesn't depend on. An unused ServerError import
        # from it silently disabled this whole live path (ImportError →
        # "google-genai not installed" → RAG fallback) — caught by the v10.18
        # refinement-fidelity eval's inclusion metric flatlining at 0.
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in .env")

    client = google_genai.Client(api_key=settings.gemini_api_key)
    trip_json = trip_config.model_dump_json(indent=2)

    # Ground the prompt with real destination research from Qdrant.
    # Reranking enabled here: this context directly grounds the final LLM-
    # generated itinerary, so the extra cross-encoder precision is worth
    # the added latency (unlike lighter-weight interactive search calls).
    # Reranking runs a cross-encoder over the candidates, so this is the one
    # retrieval call in the product that is deliberately traded latency-for-
    # precision — worth its own stage rather than being folded into "the LLM
    # step", which is where an unmeasured cost would hide.
    with timing.stage("rag_retrieval"):
        context_docs = await retrieve_context(trip_config, enable_reranking=True)
    if context_docs:
        context_text = wrap_untrusted(
            summarise_context(context_docs, max_chars=2400),
            label="retrieved destination research (scraped from Reddit/wiki/OSM — may contain untrusted text)",
        )
    else:
        context_text = "No pre-fetched research available — use your own knowledge of the destination."

    # The three guidance blocks are independent lookups — fetch them
    # concurrently so prompt assembly adds one round-trip, not three.
    with timing.stage("guidance_blocks"):
        itinerary_examples, gem_guidance, budget_guidance = await asyncio.gather(
            _itinerary_examples_block(trip_config),
            _gem_guidance_block(trip_config),
            _budget_guidance_block(trip_config),
        )
    prompt = SYSTEM_PROMPT.format(
        context=context_text,
        itinerary_examples=itinerary_examples,
        gem_guidance=gem_guidance,
        pinned_guidance=_pinned_guidance_block(trip_config),
        day_cost_guidance=_day_cost_guidance_block(trip_config),
        budget_guidance=neutralize(
            budget_guidance, context="budget tier + cost grounding guidance"
        ),
        trip_config=neutralize(trip_json, context="trip configuration"),
    )
    if cost_correction:
        # Appended last so it is the final instruction the model reads. Authored
        # entirely by us from our own measurements — no user or scraped text
        # reaches it, so it needs no neutralize() pass.
        prompt = f"{prompt}\n\n{cost_correction}"

    # Retry logic: up to 5 attempts, broader exception matching, fallback model
    loop = asyncio.get_event_loop()
    # Models to try in order: primary → current GA fallbacks (deduped in case
    # the primary IS one of them). Fallback ids must be GA models: a retired
    # preview id ("gemini-2.5-flash-lite-preview-06-17") 404'd and aborted the
    # whole chain before the next fallback was tried — caught by the first
    # v10.18 live eval run.
    models_to_try = list(dict.fromkeys(
        [settings.gemini_model, "gemini-2.5-flash", "gemini-2.0-flash"]
    ))
    # ⚠️ Deadline-aware cascade (⭐ FIXED — was previously able to spend
    # 5+10+20+40 = 75s of *sleeping* per model, 225s across all three, against
    # a 120s request timeout — a live prod trace showed exactly this: 7+
    # filler-message ticks before a guaranteed `LLM_TIMEOUT`, `_fallback_itinerary()`
    # (cache → RAG skeleton → mock) never reached at all. We now track wall-clock
    # elapsed against `settings.llm_timeout_seconds` (minus a safety margin so the
    # fallback call itself, and response serialisation, still have time to run)
    # and break out of the whole cascade — not just the current model — the
    # moment a scheduled sleep would blow the budget, raising so the caller's
    # `except Exception` in `_generate_itinerary_inner` reaches the graceful
    # fallback instead of running out the router's clock.
    # `tests/unit/test_itinerary_timing.py` measures the schedule rather than
    # restating it.
    max_attempts = 5
    _deadline_margin_seconds = 10.0
    _cascade_deadline = (
        loop.time() + max(settings.llm_timeout_seconds - _deadline_margin_seconds, 0)
    )

    last_error: Exception | None = None
    for model_name in models_to_try:
        for attempt in range(max_attempts):
            try:
                def _call_sync(m: str = model_name):  # noqa: E731
                    return client.models.generate_content(
                        model=m,
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(
                            temperature=0.4,
                            response_mime_type="application/json",
                        ),
                    )

                # Counted before the await, so an attempt that dies still
                # shows up — a cascade that burned four calls and timed out
                # must not read as "one attempt".
                timing.increment("llm_attempts")
                with timing.stage("llm_api"):
                    response = await loop.run_in_executor(None, _call_sync)
                timing.label("llm_model", model_name)
                track_gemini_usage(response, model=model_name, purpose="itinerary_generation")
                text = response.text

                # Strip markdown fences if Gemini adds them despite response_mime_type
                cleaned = text.strip()
                if cleaned.startswith("```"):
                    cleaned = "\n".join(cleaned.split("\n")[1:])
                if cleaned.endswith("```"):
                    cleaned = "\n".join(cleaned.split("\n")[:-1])
                parsed = json.loads(cleaned)
                # Threaded through so _generate_itinerary_inner can mark the
                # whole response "live_unverified" instead of "live" when
                # there was nothing in our corpus to ground this destination
                # at all — a live call with no context is not the same
                # guarantee as one grounded in retrieved research.
                parsed["_context_grounded"] = bool(context_docs)
                return parsed

            except json.JSONDecodeError as e:
                raise RuntimeError(f"Gemini returned invalid JSON: {e}") from e

            except Exception as e:
                kind = _classify_gemini_error(str(e))
                if kind == "transient" and attempt < max_attempts - 1:
                    wait_time = min(5 * (2 ** attempt), 60)  # 5s, 10s, 20s, 40s, 60s cap
                    # Deadline check BEFORE sleeping: if this sleep would run
                    # past the budget, stop retrying now — surfacing to
                    # `_generate_itinerary_inner`'s except block for the
                    # graceful fallback — rather than sleeping anyway and
                    # having the router's `asyncio.wait_for` cancel us
                    # mid-sleep, which produces a bare `LLM_TIMEOUT` instead.
                    if loop.time() + wait_time >= _cascade_deadline:
                        logger.error(
                            "Gemini transient error on %s (attempt %d/%d); next backoff "
                            "(%ds) would exceed the request deadline — aborting cascade "
                            "for graceful fallback instead of timing out.",
                            model_name, attempt + 1, max_attempts, wait_time,
                        )
                        last_error = e
                        raise RuntimeError(
                            f"Gemini itinerary generation aborted before deadline: {last_error}"
                        ) from last_error
                    logger.warning("Gemini transient error on %s (attempt %d/%d). Retrying in %ds…", model_name, attempt + 1, max_attempts, wait_time)
                    # Backoff is tracked apart from `llm_api` on purpose: "the
                    # provider was slow" and "we chose to wait" need different
                    # fixes, and this schedule (5/10/20/40s) can dominate a
                    # request without a single slow call.
                    with timing.stage("llm_retry_sleep"):
                        await asyncio.sleep(wait_time)
                    timing.increment("llm_retries")
                    last_error = e
                    continue
                elif kind == "transient":
                    # exhausted retries on this model → try next model
                    logger.error("Gemini model %s failed after %d attempts, trying fallback…", model_name, max_attempts)
                    last_error = e
                    break
                elif kind == "model_missing":
                    # Retired/renamed model id — retrying it is pointless, but
                    # the next fallback model may work fine. Skip immediately.
                    logger.error("Gemini model %s unavailable (%s); trying fallback…", model_name, e)
                    last_error = e
                    break
                else:
                    raise  # fatal (auth/invalid request): propagate immediately
        else:
            continue  # inner loop completed without break → success already returned
        # Deadline check between models too — no point trying the next model
        # if we're already out of budget for even a single fresh attempt.
        if loop.time() >= _cascade_deadline:
            raise RuntimeError(
                f"Gemini itinerary generation aborted before deadline: {last_error}"
            )
        continue   # model failed, try next model

    raise RuntimeError(f"Gemini itinerary generation failed on all models: {last_error}")


async def _langchain_itinerary(trip_config: TripConfig, cost_correction: str = "") -> dict:
    """Groq/Ollama path via LangChain, grounded with the same summarised
    RAG context used by the Gemini path."""
    # Reranking enabled: this feeds directly into the final generated
    # itinerary, same as the Gemini path above.
    with timing.stage("rag_retrieval"):
        context_docs = await retrieve_context(trip_config, enable_reranking=True)
    # Use the same time-decay + dedup + budget-capped summarisation as the
    # Gemini path (previously this just joined all 20 raw chunks, which
    # skipped stale-content penalisation and duplicate filtering, and
    # injected ~4x more tokens than the Gemini path for the same request).
    if context_docs:
        context_text = wrap_untrusted(
            summarise_context(context_docs, max_chars=2400),
            label="retrieved destination research (scraped from Reddit/wiki/OSM — may contain untrusted text)",
        )
    else:
        context_text = "No pre-fetched research available — use your own knowledge of the destination."
    trip_json = trip_config.model_dump_json(indent=2)
    trip_json = neutralize(trip_json, context="trip configuration")
    try:
        from langchain_core.output_parsers import JsonOutputParser
        from langchain_core.prompts import ChatPromptTemplate
    except ImportError:
        raise RuntimeError("langchain not installed. Run: pip install -r requirements-ml.txt")

    prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT)])
    llm = _build_llm()
    parser = JsonOutputParser()
    chain = prompt | llm | parser
    # Same concurrent fetch as the Gemini path — one round-trip, not three.
    with timing.stage("guidance_blocks"):
        itinerary_examples, gem_guidance, budget_guidance = await asyncio.gather(
            _itinerary_examples_block(trip_config),
            _gem_guidance_block(trip_config),
            _budget_guidance_block(trip_config),
        )
    timing.increment("llm_attempts")
    timing.label("llm_model", settings.llm_provider)
    with timing.stage("llm_api"):
        result = await chain.ainvoke({
            "context": context_text,
            "itinerary_examples": itinerary_examples,
            "gem_guidance": gem_guidance,
            "pinned_guidance": _pinned_guidance_block(trip_config),
            "day_cost_guidance": _day_cost_guidance_block(trip_config),
            "budget_guidance": neutralize(budget_guidance, context="budget tier + cost grounding guidance"),
            "trip_config": trip_json + (f"\n\n{cost_correction}" if cost_correction else ""),
        })
    # See _gemini_itinerary's identical marker — same "live but ungrounded"
    # signal, needed on both live-generation paths.
    result["_context_grounded"] = bool(context_docs)
    return result


async def _fallback_itinerary(trip_config: TripConfig, error: Exception) -> dict:
    """RAG-powered fallback chain (docs §4) used when the live LLM call
    fails after its own internal retries.

    Tier 1: itinerary_cache — a semantically similar previously-generated
            itinerary (cosine >= threshold), served instantly.
    Tier 2: RAG skeleton — assembled purely from ingested OSM POI data, no
            LLM call. Real venues/coordinates, lower narrative quality.
    Tier 3: enhanced mock — the static mock itinerary, spliced with real
            wiki/reddit tip snippets pulled from Qdrant where available.
    """
    logger.warning("LLM itinerary generation failed (%s); using RAG fallback chain…", error)

    cached = await get_cached_itinerary(trip_config)
    if cached is not None:
        return cached

    skeleton = await rag_skeleton_itinerary(trip_config)
    if skeleton is not None:
        return skeleton

    tip_texts: list[str] = []
    try:
        context_docs = await retrieve_context(trip_config)
        tip_texts = [d["text"][:160] for d in context_docs[:6]]
    except Exception:
        pass
    raw = _mock_itinerary(trip_config, tip_texts=tip_texts)
    raw["_from_fallback"] = "enhanced_mock"
    return raw


async def generate_itinerary(trip_config: TripConfig) -> ItineraryResponse:
    # The whole body sits inside `track()` so the timing record is emitted from
    # the `finally` below on *every* exit path — including the one that matters
    # most. The router wraps this call in `asyncio.wait_for(...,
    # llm_timeout_seconds)`, so a slow generation ends as a CancelledError here,
    # and instrumenting only the success path would have measured everything
    # except the requests that ran out of time.
    with timing.track("generate_itinerary") as timings:
        try:
            return await _generate_itinerary_inner(trip_config, timings)
        finally:
            timing.log_timings(
                logger, timings,
                slow_threshold_seconds=settings.slow_itinerary_threshold_seconds,
            )


async def _generate_itinerary_inner(
    trip_config: TripConfig, timings: timing.RequestTimings
) -> ItineraryResponse:
    timings.label("provider", settings.llm_provider)
    # Set only by the live path; stays None for mock/cache/fallback, whose costs
    # come from code we control rather than a model that can drift currency.
    cost_warning: str | None = None
    if settings.llm_provider == "mock":
        raw = _mock_itinerary(trip_config)
        raw.setdefault("_from_fallback", "mock")
    else:
        dest = trip_config.destination.city if trip_config.destination else ""
        if dest:
            try:
                from services.destination_ingestion import ensure_destination_ingested
                # First-ever request for a destination runs Overpass +
                # Wikivoyage + embeddings inline, blocking this user's response
                # for everyone who arrives first. This stage is what says how
                # often that happens and what it costs.
                with timing.stage("ingestion"):
                    await ensure_destination_ingested(dest)
            except Exception:
                logger.warning("destination ingestion gatekeeper failed for %r", dest, exc_info=True)
        async def _generate(correction: str = "") -> dict:
            if settings.llm_provider == "gemini":
                return await _gemini_itinerary(trip_config, cost_correction=correction)
            return await _langchain_itinerary(trip_config, cost_correction=correction)

        try:
            raw = await _generate()
            # Cost sanity BEFORE the cache write — caching a wrong-currency or
            # wrong-direction itinerary would serve the defect to every later
            # fallback for this trip shape, long after the bad run is forgotten.
            problem = _cost_sanity_problem(raw, trip_config)
            if problem:
                logger.warning("Itinerary costs rejected, regenerating once: %s", problem)
                timing.increment("cost_sanity_retries")
                with timing.stage("cost_retry"):
                    retry_raw = await _generate(_cost_correction_block(problem))
                retry_problem = _cost_sanity_problem(retry_raw, trip_config)
                if not retry_problem:
                    raw, problem = retry_raw, None
                else:
                    # Keep the FIRST result. A second bad answer is not an
                    # improvement, and swapping one defect for another loses
                    # the only thing we know about this one. The surviving
                    # `problem` becomes a user-visible warning below — never
                    # present unreliable costs as if they were checked.
                    logger.warning("Regenerated itinerary still fails cost sanity: %s", retry_problem)
                    timing.increment("cost_sanity_retries_failed")
            cost_warning = problem
            # A live call that had nothing in our corpus to ground itself in
            # is not the same guarantee as a normal live generation — mark it
            # before caching so the disclosure survives into any later
            # cache-served response for this trip shape too.
            if raw.get("_context_grounded") is False:
                raw.setdefault("_from_fallback", "live_unverified")
        except Exception as llm_error:
            with timing.stage("fallback"):
                raw = await _fallback_itinerary(trip_config, llm_error)
        else:
            # Cache successful LLM-generated itineraries for future
            # fallback use (best-effort — never blocks/fails the response).
            with timing.stage("cache_store"):
                await store_itinerary(trip_config, raw)

    with timing.stage("post_processing"):
        days = _parse_days(raw.get("days", []))
        days = apply_kid_safety_filter(days, trip_config)
        days = inject_persona_modules(days, trip_config)
        # After the filters so an enforced pin can't be re-dropped downstream.
        days = _enforce_pins(days, trip_config)
        # Per-item provenance: only meaningful on a genuine live LLM call —
        # mock/cache/rag_skeleton items are already either curated or
        # OSM-sourced by construction, so ItineraryItem.verified's default of
        # True is correct for them without running a check that would just
        # cost a Qdrant round-trip to confirm what's already guaranteed.
        if not raw.get("_from_fallback") or raw.get("_from_fallback") == "live_unverified":
            with timing.stage("item_verification"):
                try:
                    # Bounded so a slow/stalled Qdrant round-trip degrades to
                    # "not checked this time" instead of adding open-ended
                    # latency to every live generation — this pass is a
                    # disclosure nicety, never worth blocking the response
                    # travellers are waiting on.
                    days = await asyncio.wait_for(
                        _flag_unverified_items(days, trip_config), timeout=3.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("Item-title verification timed out; leaving items unflagged")
        # Geo out-of-bounds check runs on every tier — pure CPU, no I/O, and
        # a coordinate glitch is worth catching even in mock/cache data.
        days = _flag_out_of_bounds_items(days, trip_config)

        scored_days = []
        for day in days:
            scored_items = [
                item.model_copy(
                    update={"alignment_score": calculate_alignment_score(item, trip_config)}
                )
                for item in day.items
            ]
            day.items = scored_items
            scored_days.append(day)

    # ⭐ Day hero photos are NOT fetched here any more. v10.47's instrumentation
    # flagged this batch as the clearest candidate for moving off the critical
    # path, and the answer turned out to be simpler than tuning it: the photos
    # are only ever rendered by the PDF export (`ItineraryDocument.tsx`) — the
    # dashboard shows YouTube thumbnails — so every generation was awaiting a
    # metered third-party call, with a 6s timeout, for images most users never
    # see. `POST /api/day-photos` now serves them when the user presses
    # Download, and `ItineraryDay.image_*` simply stays empty until then.

    overall_score = (
        sum(i.alignment_score for d in scored_days for i in d.items)
        / max(sum(len(d.items) for d in scored_days), 1)
    )

    timings.label("generation_tier", str(raw.get("_from_fallback", "live")))
    timings.increment("days", len(scored_days))

    # Re-asked rather than threaded down from `_budget_guidance_block` through
    # three call frames and two generation paths (Gemini, LangChain) plus the
    # fallback. `ensure_entry_info` memoises per country for the life of the
    # process, so this is a dict hit — and on the fallback paths, where no
    # guidance block ran, it is the only thing that establishes coverage at all.
    entry_country = (
        (trip_config.destination.country if trip_config.destination else None)
        or trip_config.destination_country
        or ""
    )
    entry_grounded = await ensure_entry_info(entry_country)

    # A surviving cost problem is disclosed, not swallowed: the plan itself is
    # good (real places, pins honoured) and is worth showing, but its numbers
    # failed our own check twice and must not read as verified.
    warnings = (
        ["Cost estimates for this itinerary look unreliable and should be treated "
         "as rough — the plan itself is unaffected."]
        if cost_warning else []
    )

    return ItineraryResponse(
        days=scored_days,
        alignment_score=round(overall_score, 2),
        warnings=warnings,
        expense_breakdown=_parse_expense_breakdown(
            raw.get("expense_breakdown", {}), trip_config, entry_grounded=entry_grounded
        ),
        generation_tier=raw.get("_from_fallback", "live"),
    )


# ── Cost sanity, and the one retry it earns ──────────────────────────────────
#
# Two failure modes, both live-observed 2026-08-05 on Bali generations, both
# invisible to every other check because the itinerary is otherwise perfect —
# right day count, real places, pins honoured, internally consistent totals.
#
# 1. WRONG CURRENCY. One run in five returned `Rs 124,525,000` for a 6-day trip
#    on a Rs 2.4L budget, with day figures like Rs 1,800,000 — Gemini silently
#    costing in Indonesian Rupiah despite the schema saying INR. It corrupts
#    `expense_breakdown` too, not just the per-item field, so it is not
#    specific to per-day costs.
# 2. WRONG DIRECTION. A day the user asked to be made CHEAPER coming back at or
#    above the cost of the trip's other days. Scale can look perfectly normal
#    here — the number is simply wrong, which is the more insidious of the two.
#
# The anchor for (1) is deliberately budget-free: per-person-per-day. A stated
# budget cannot be the yardstick, because the entire feasibility gate exists
# for trips whose real cost far exceeds what the user typed. Bounds are set
# very wide — this is a unit-error detector, not a price opinion.
_MAX_PLAUSIBLE_INR_PER_PERSON_PER_DAY = 500_000
_MIN_PLAUSIBLE_INR_PER_PERSON_PER_DAY = 200

# 🔵 KNOWN GAP (2026-08-05): these bounds only catch gross unit/direction
# errors, not a plausible-looking wrong number — live eval showed ~1 in 5
# runs slip through with a total that is off by 2-3x but still inside
# [_MIN_PLAUSIBLE, _MAX_PLAUSIBLE]. `core.budget_estimator
# .estimate_bare_minimum_budget` is the obvious second anchor: it already
# derives a deterministic flights+stay+food floor for this exact
# destination/group/duration, independent of the model's own number, so a
# total far below (or absurdly above a reasonable multiple of) that floor
# would be a much tighter check than a fixed per-person-per-day band. Not
# wired in yet — it costs an extra call on the generation path, and is only
# worth it once costs are user-facing beyond an estimate (see
# docs/NEXT_SESSION_TODO.md).


def _cost_sanity_problem(raw: dict, trip_config: TripConfig) -> str | None:
    """Describe what is wrong with this itinerary's costs, or None if fine.

    The string is fed back to the model as a correction, so it names the
    defect in the model's own terms rather than ours.
    """
    breakdown = raw.get("expense_breakdown") or {}
    total = _coerce_cost_inr(breakdown.get("total_inr"))
    days = raw.get("days") or []
    group = trip_config.group
    people = max(1, group.adults + group.seniors + len(group.kids))
    n_days = max(1, len(days))

    if total:
        per_person_per_day = total / (people * n_days)
        if per_person_per_day > _MAX_PLAUSIBLE_INR_PER_PERSON_PER_DAY:
            return (
                f"the total came to INR {total:,} for {people} people over {n_days} days "
                f"— about INR {per_person_per_day:,.0f} per person per day, which is far "
                "too high for any real trip. This normally means the figures were given "
                "in the destination's local currency instead of Indian Rupees"
            )
        if per_person_per_day < _MIN_PLAUSIBLE_INR_PER_PERSON_PER_DAY:
            return (
                f"the total came to only INR {total:,} for {people} people over "
                f"{n_days} days, which is far too low to be a real trip cost"
            )

    # Direction: a day asked to be cheaper must actually BE cheaper than the
    # rest of the trip. Compared against the other days rather than against a
    # previous generation, because each generation is independent — there is no
    # "before" to diff against inside a single call.
    prefs = getattr(trip_config, "day_cost_preferences", None) or []
    if prefs and len(days) > 1:
        by_day = {
            _coerce_cost_inr(d.get("day_number")): sum(
                _coerce_cost_inr(i.get("estimated_cost_inr")) for i in (d.get("items") or [])
            )
            for d in days
        }
        if any(by_day.values()):        # all-zero costs is a separate problem
            for pref in prefs:
                target = by_day.get(pref.day_number)
                others = [c for d, c in by_day.items() if d != pref.day_number]
                if target is None or not others:
                    continue
                avg_other = sum(others) / len(others)
                if pref.direction == "cheaper" and target >= avg_other:
                    return (
                        f"day {pref.day_number} was supposed to be the CHEAPER day, but it "
                        f"costs INR {target:,} while the other days average INR "
                        f"{avg_other:,.0f} — it must come out clearly below them"
                    )
                if pref.direction == "pricier" and target <= avg_other:
                    return (
                        f"day {pref.day_number} was supposed to be the day to SPEND MORE, "
                        f"but it costs INR {target:,} while the other days average INR "
                        f"{avg_other:,.0f} — it must come out clearly above them"
                    )
    return None


def _cost_correction_block(problem: str) -> str:
    """The corrective instruction appended to a regeneration prompt."""
    return (
        "🔴 COST CORRECTION — your previous answer for this exact trip was rejected:\n"
        f"{problem}.\n"
        "Regenerate the whole itinerary. EVERY monetary figure — every item's "
        "`estimated_cost_inr` and every field in `expense_breakdown` — must be in "
        "INDIAN RUPEES (INR), never the destination's local currency, and must stay "
        "in INR consistently across the entire response. Convert at a realistic rate "
        "if you are thinking in local prices. Keep the same places, the same pinned "
        "must-includes and the same structure — only the costs were wrong."
    )


_COST_DIGITS_RE = re.compile(r"\d+")


def _coerce_cost_inr(raw: object) -> int:
    """Best-effort int for a per-item cost the model may have typed loosely.

    Accepts 500, 500.0, "500", "₹500", "500 INR", "1,200"; maps "free"/None/
    anything unparseable to 0. Negatives clamp to 0 — a negative cost is
    nonsense and the field rejects it, which would sink the whole itinerary.
    """
    if isinstance(raw, bool):          # bool is an int subclass; never a cost
        return 0
    if isinstance(raw, int | float):
        return max(0, int(raw))
    if isinstance(raw, str):
        digits = "".join(_COST_DIGITS_RE.findall(raw.replace(",", "")))
        return int(digits) if digits else 0
    return 0


def _parse_days(raw_days: list[dict]) -> list[ItineraryDay]:
    days = []
    for rd in raw_days:
        items = []
        for ri in rd.get("items", []):
            loc = ri.get("location", {})
            items.append(ItineraryItem(
                id=ri.get("id") or str(uuid.uuid4()),
                time_start=ri.get("time_start", "09:00"),
                time_end=ri.get("time_end", "10:00"),
                title=ri.get("title", ""),
                description=ri.get("description", ""),
                location=ItineraryItemLocation(
                    lat=loc.get("lat", 0.0),
                    lon=loc.get("lon", 0.0),
                    address=loc.get("address", ""),
                ),
                local_name=ri.get("local_name", ""),
                tags=ri.get("tags", []),
                # Coerced defensively: the model occasionally answers "₹500",
                # "free" or a float here rather than an int, and a ValidationError
                # would discard the ENTIRE itinerary over one cost estimate.
                # Falling back to 0 loses a figure; raising loses the trip.
                estimated_cost_inr=_coerce_cost_inr(ri.get("estimated_cost_inr")),
                booking_url=ri.get("booking_url", ""),
                youtube_video_id=ri.get("youtube_video_id", ""),
                youtube_search_query=ri.get("youtube_search_query", ""),
            ))
        days.append(ItineraryDay(
            day_number=rd.get("day_number", 1),
            date=rd.get("date", ""),
            theme=rd.get("theme", ""),
            items=items,
        ))
    return days

