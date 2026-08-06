"""Feasibility chain — uses Gemini to estimate trip costs and check budget."""
from __future__ import annotations

import asyncio
import json

from core.budget_estimator import estimate_bare_minimum_budget
from core.budget_tiers import budget_tier_prompt_hint
from core.config import settings
from core.cost_grounding import accommodation_cost_grounding_hint, flight_cost_grounding_hint
from core.llm_client import track_gemini_usage
from core.prompt_guard import neutralize
from models.feasibility import AlternativeDestination, CostBreakdown, FeasibilityResponse
from models.trip import TripConfig
from services.visa import entry_cost_grounding

FEASIBILITY_PROMPT = """\
You are a travel cost expert. Estimate the realistic total cost (in Indian Rupees) for the
trip described below for travelers departing from India.

Provide cost estimates based on average market rates. Be conservative (lean slightly higher).

TRIP DETAILS:
{trip_config}

{budget_tier_hint}

{cost_grounding_hint}

OUTPUT SCHEMA (valid JSON only, no markdown):
{{
  "flights_inr": <round-trip economy flight cost per person × total passengers>,
  "visa_inr": <total MANDATORY entry cost for all passengers — see ENTRY COSTS rule — 0 if none>,
  "accommodation_inr": <avg nightly rate in INR × number of nights × number of rooms needed>,
  "daily_expenses_inr": <food + activities + local transport per person per day × days × people>,
  "total_estimated_inr": <sum of all above>,
  "alternatives": [
    {{
      "city": "string",
      "country": "string",
      "estimated_total_inr": <integer>,
      "why_cheaper": "short reason e.g. No visa required, budget flights available",
      "similar_experiences": ["experience1", "experience2"]
    }}
  ]
}}

RULES:
- Convert all costs to INR.
- Use average economy class fares from major Indian airports.
- For accommodation, use the style specified (hostel/budget/boutique/luxury), and the BUDGET TIER GUIDANCE above.
- If a FLIGHT COST GROUNDING or COMMUNITY-REPORTED rate range is given above, treat it as a strong sanity check — do not stray far from it without good reason.
- If budget is clearly insufficient, suggest 2-3 cheaper alternatives that offer similar experiences.
- If budget is sufficient, still suggest 1-2 alternative destinations for variety.
- Keep alternatives realistic for Indian passport holders.

ENTRY COSTS (`visa_inr`) — the traveller holds an INDIAN passport:
- Include every MANDATORY per-person cost of entry: visa or e-visa fees,
  permits, and compulsory per-night tourism levies. Not only "the visa fee".
- Use the rate for INDIAN nationals, which is frequently far lower than the
  rate for other passports and is often zero. Bhutan charges most visitors USD
  100 per night but Indian nationals ₹1,200 per night with no visa — quoting
  the international rate is a sevenfold error.
- Multiply per-night levies by nights AND by the people who pay them; check
  whether children are exempt before charging them in full.
- Base this on the ENTRY-COST GROUNDING above. When that block is absent your
  figure is discarded server-side and shown as "not available", so do not fill
  the gap with a guess.
- Do not fold entry costs into `daily_expenses_inr` to compensate.

- Return ONLY valid JSON matching the schema above.
"""


async def _check_destination_exists(trip_config: TripConfig) -> bool | None:
    """Geocode-validate the destination as a cheap, early "does this place
    exist at all" check — distinct from and prior to budget feasibility,
    since a nonexistent destination (the deck's "Wizarding World Goa" case)
    has no meaningful cost to estimate. Returns None when there's no single
    named place to check yet (destination_mode "country"/"exploring" — those
    describe a whole country or nothing at all, not a geocodable point) OR
    when the destination already carries real lat/lon.

    That last skip matters for latency: by the time this runs, the wizard
    chat flow (wizard_chat_chain.py::_resolve_origin_destination_coords) has
    almost always already geocoded this exact destination and stored real
    coordinates on it — Nominatim's own usage policy caps every call
    (search + reverse) at 1 req/sec process-wide (services/geocode.py's
    _rate_limited_get), so redundantly re-geocoding an already-resolved
    destination on every feasibility check serialises a live network round
    trip in front of the LLM call for no new information. Only destinations
    that reach here with (0, 0) — meaning nothing has resolved them yet —
    pay the live lookup cost.

    Reuses the same geocode_city() lookup (Nominatim + Wikipedia fallback)
    already used everywhere else in the app, so a "yes, real" or "no" here
    means the same thing it would to destination ingestion. Never raises —
    a geocoding hiccup must not block the feasibility check; it degrades to
    "not checked" (None), not a false failure."""
    if trip_config.destination_mode and trip_config.destination_mode != "fixed":
        return None
    dest = trip_config.destination
    city = dest.city if dest else ""
    if not city:
        return None
    if dest and (dest.lat != 0.0 or dest.lon != 0.0):
        # Already resolved to real coordinates elsewhere in the flow — that
        # only happens for a destination Nominatim/Wikipedia could find.
        return True
    from services.geocode import geocode_city

    try:
        await geocode_city(city)
        return True
    except Exception:
        return False


async def check_feasibility(
    trip_config: TripConfig, skip_destination_check: bool = False
) -> FeasibilityResponse:
    """Call Gemini to estimate trip costs and check budget feasibility."""
    destination_verified: bool | None = None
    if not skip_destination_check:
        destination_verified = await _check_destination_exists(trip_config)
        if destination_verified is False:
            dest_name = trip_config.destination.city if trip_config.destination else "this place"
            return FeasibilityResponse(
                feasible=False,
                verdict=(
                    f"We could not verify that \"{dest_name}\" is a real place — it may be "
                    "misspelled, or it may not exist. You can go back and check the spelling, "
                    "or continue anyway if you're confident it's right."
                ),
                budget_inr=int(trip_config.budget.amount),
                breakdown=CostBreakdown(),
                destination_verified=False,
            )

    # Calculate total people
    group = trip_config.group if isinstance(trip_config.group, dict) else trip_config.group.__dict__
    if hasattr(trip_config.group, 'adults'):
        adults = trip_config.group.adults
        seniors = trip_config.group.seniors
        kids = len(trip_config.group.kids) if trip_config.group.kids else 0
    else:
        adults = group.get('adults', 1)
        seniors = group.get('seniors', 0)
        kids = len(group.get('kids', []))
    total_people = adults + seniors + kids

    # Calculate trip nights
    dates = trip_config.dates if isinstance(trip_config.dates, dict) else trip_config.dates.__dict__
    # `TripConfig.dates` is declared as a plain dict, but this chain is also
    # driven by the eval harness with model-shaped configs -- getattr tolerates
    # both without the attribute access being dead code under the declared type.
    start = getattr(trip_config.dates, 'start', None) or dates.get('start') or dates.get('start_date')
    end = getattr(trip_config.dates, 'end', None) or dates.get('end') or dates.get('end_date')

    nights = 4  # default
    if start and end:
        try:
            from datetime import date
            nights = max(1, (date.fromisoformat(end) - date.fromisoformat(start)).days)
        except Exception:
            pass

    dest = trip_config.destination.city if trip_config.destination else "the destination"
    budget_inr = int(trip_config.budget.amount)

    trip_summary = {
        "destination": dest,
        "origin": trip_config.origin.city,
        "nights": nights,
        "total_people": total_people,
        "adults": adults,
        "kids_count": kids,
        "seniors": seniors,
        "accommodation_style": trip_config.accommodation.style[0] if trip_config.accommodation.style else "mid-range hotel",
        "budget_inr": budget_inr,
        "purpose": trip_config.purpose,
    }

    if settings.llm_provider == "mock":
        return _mock_feasibility(trip_summary, budget_inr)

    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        raise RuntimeError("google-genai not installed.")

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    # Free-tools-only budget curation (⭐ NEW): persona/purpose budget-tier
    # guidance + a real-distance flight heuristic + community-reported price
    # mentions pulled from the existing free RAG collections. Best-effort —
    # a retrieval hiccup degrades to "no extra grounding", never blocks the
    # feasibility check.
    budget_tier_hint = budget_tier_prompt_hint(trip_config)
    # The visa lookup joins the existing gather rather than being awaited
    # separately, so grounding the entry cost costs no extra wall-clock on a
    # path that already runs two retrievals concurrently.
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
        entry_hint, entry_grounded = entry
    except Exception:
        flight_hint, accommodation_hint, entry_hint = "", "", ""
        entry_grounded = False
    cost_grounding_hint = "\n\n".join(
        h for h in (flight_hint, accommodation_hint, entry_hint) if h
    )

    client = google_genai.Client(api_key=settings.gemini_api_key)
    prompt = FEASIBILITY_PROMPT.format(
        trip_config=neutralize(json.dumps(trip_summary, indent=2), context="trip summary"),
        budget_tier_hint=neutralize(budget_tier_hint, context="budget tier guidance"),
        cost_grounding_hint=neutralize(cost_grounding_hint, context="free-tools cost grounding") if cost_grounding_hint else "No community-reported price data available — rely on general market-rate knowledge.",
    )

    def _call_sync():
        return client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, _call_sync)
    track_gemini_usage(response, model=settings.gemini_model, purpose="feasibility_check")
    text = response.text

    # Parse response
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:])
    if cleaned.endswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[:-1])

    data = json.loads(cleaned)
    bare_minimum = await _safe_bare_minimum(trip_config)
    return _build_response(
        data,
        budget_inr,
        bare_minimum,
        trip_config,
        entry_grounded=entry_grounded,
        destination_verified=destination_verified,
    )


def _traveller_level_hint_text(trip_config: TripConfig) -> str:
    """Synthesises a hint string from structured tier signals already on the
    trip config (personas, accommodation style) so the deterministic floor
    picks up a premium/economical preference even when we don't have the
    user's raw chat text at this call site (unlike budget_estimate_prompt_hint,
    which runs during the chat turn itself). Without this, the floor always
    assumed mid-range, which could sit far below — and look inconsistent
    with — a premium-aware LLM cost estimate."""
    parts = list(trip_config.personas) + list(trip_config.accommodation.style) + list(trip_config.splurge_categories)
    return " ".join(parts)


async def _safe_bare_minimum(trip_config: TripConfig) -> dict | None:
    """Best-effort deterministic bare-minimum estimate (flights+stay+food) used
    as a floor against the LLM's own cost guess — never blocks the feasibility
    check if it fails for any reason (e.g. group size still unknown)."""
    try:
        hint_text = _traveller_level_hint_text(trip_config)
        return await estimate_bare_minimum_budget(trip_config.model_dump(), hint_text)
    except Exception:
        return None


def _build_response(
    data: dict,
    budget_inr: int,
    bare_minimum: dict | None = None,
    trip_config: TripConfig | None = None,
    *,
    entry_grounded: bool = False,
    destination_verified: bool | None = None,
) -> FeasibilityResponse:
    llm_flights = int(data.get("flights_inr", 0))
    llm_accommodation = int(data.get("accommodation_inr", 0))
    total = int(data.get("total_estimated_inr", 0))

    # Already-booked flights/accommodation (⭐ NEW): swap the LLM's guessed
    # component for the user's real paid amount, since that's a sunk cost
    # already covered, not something still owed against the stated budget.
    prebooked_flights = getattr(trip_config, "prebooked_flights_inr", None) if trip_config else None
    prebooked_accommodation = getattr(trip_config, "prebooked_accommodation_inr", None) if trip_config else None
    if prebooked_flights is not None:
        total = total - llm_flights + prebooked_flights
        llm_flights = prebooked_flights
    if prebooked_accommodation is not None:
        total = total - llm_accommodation + prebooked_accommodation
        llm_accommodation = prebooked_accommodation

    # Deterministic free-tools floor (⭐ NEW): the LLM's cost guess can
    # occasionally undershoot for an unusual destination/group combo. Our
    # hand-authored bare-minimum estimate (flights+stay+food only) acts as a
    # floor — if the LLM total falls short of it, use the floor instead so
    # "feasible" never means "feasible according to an optimistic guess".
    floor_used = False
    bare_minimum_inr = bare_minimum["total_inr"] if bare_minimum else None
    if bare_minimum_inr is not None and bare_minimum_inr > total:
        total = bare_minimum_inr
        floor_used = True

    feasible = total <= budget_inr

    breakdown = CostBreakdown(
        flights_inr=llm_flights,
        # 🔴 The model's figure is kept only when the visa corpus actually
        # covered this country; otherwise None, meaning "not available" — never
        # 0, which would claim entry is free. Same structural gate as
        # `chains/itinerary_chain.py::_parse_expense_breakdown`, for the same
        # reason: Bhutan produced ₹41,000 of ungrounded "visa" on a 5-day trip
        # (the international USD 100/night levy, for a traveller who needs no
        # visa and pays ₹1,200/night), and a model cannot tell us when it is
        # guessing.
        visa_inr=int(data.get("visa_inr", 0)) if entry_grounded else None,
        accommodation_inr=llm_accommodation,
        daily_expenses_inr=int(data.get("daily_expenses_inr", 0)),
        total_estimated_inr=total,
    )

    alternatives = [
        AlternativeDestination(
            city=a.get("city", ""),
            country=a.get("country", ""),
            estimated_total_inr=int(a.get("estimated_total_inr", 0)),
            why_cheaper=a.get("why_cheaper", ""),
            similar_experiences=a.get("similar_experiences", []),
        )
        for a in data.get("alternatives", [])
    ]

    if feasible:
        verdict = f"✅ Budget looks sufficient! Estimated trip cost is ₹{total:,}."
        buffer = budget_inr - total
        shortfall = 0
    else:
        shortfall = total - budget_inr
        buffer = 0
        floor_note = " (based on our bare-minimum flights+stay+food floor)" if floor_used else ""
        verdict = f"⚠️ Budget may be short by ₹{shortfall:,}. Estimated minimum is ₹{total:,}{floor_note}."

    return FeasibilityResponse(
        feasible=feasible,
        verdict=verdict,
        budget_inr=budget_inr,
        breakdown=breakdown,
        shortfall_inr=shortfall,
        buffer_inr=buffer,
        bare_minimum_inr=bare_minimum_inr,
        alternatives=alternatives,
        destination_verified=destination_verified,
    )


def _mock_feasibility(trip_summary: dict, budget_inr: int) -> FeasibilityResponse:
    """Mock response for dev mode."""
    nights = trip_summary.get("nights", 4)
    people = trip_summary.get("total_people", 2)

    flights = 35000 * people
    # None, matching what the live path produces for an uncovered country: the
    # mock runs with no corpus behind it, so a flat ₹6,500/person here would be
    # the one surface showing a figure production would have suppressed — dev
    # and eval runs would validate behaviour that never ships.
    visa = None
    accommodation = 4500 * nights
    daily = 3000 * nights * people
    total = flights + (visa or 0) + accommodation + daily

    alternatives = [
        AlternativeDestination(
            city="Bali",
            country="Indonesia",
            estimated_total_inr=int(total * 0.6),
            why_cheaper="No visa required for Indians, budget flights from major cities",
            similar_experiences=["Beaches", "Temples", "Nightlife"],
        ),
        AlternativeDestination(
            city="Bangkok",
            country="Thailand",
            estimated_total_inr=int(total * 0.55),
            why_cheaper="Visa-on-arrival, affordable street food and stays",
            similar_experiences=["Street food", "Temples", "Shopping"],
        ),
    ]

    return _build_response(
        {
            "flights_inr": flights,
            "visa_inr": visa,
            "accommodation_inr": accommodation,
            "daily_expenses_inr": daily,
            "total_estimated_inr": total,
            "alternatives": [a.model_dump() for a in alternatives],
        },
        budget_inr,
    )
