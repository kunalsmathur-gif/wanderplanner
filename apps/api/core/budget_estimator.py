"""Free-tools bare-minimum budget estimator for the wizard chat.

Used only when the user asks Anya to *recommend/suggest* a budget (rather
than giving their own number). Produces a deterministic, hand-authored
estimate covering flights + stay + food (the agreed "bare minimum") instead
of letting the LLM pattern-match a flat number off the Indian-cultural-context
budget-tier table (that table is meant for *parsing* user-stated amounts like
"a budget trip", not for *generating* recommendations).

Design constraints (per product decision): free tools only, no paid pricing
APIs. Everything here is either arithmetic or a hand-authored lookup table —
consistent with `core/budget_tiers.py` and `core/cost_grounding.py`.

The estimate deliberately requires group size to be known before it will
produce a number — if group size is missing, `budget_estimate_prompt_hint()`
returns clarifying-question guidance instead of a number, so the LLM asks
before it quotes (this is the actual UX bug being fixed: Anya was quoting
a flat 40,000 INR "budget trip" figure before even knowing headcount).
"""
from __future__ import annotations

from datetime import date
from typing import Any

# ---------------------------------------------------------------------------
# Destination cost tier (hand-authored — reflects real-world cost of living +
# INR conversion factor for Indian travellers; the same "premium destinations
# stay premium" signal used in cost_grounding.py's distance bands, but here
# keyed on destination identity rather than distance).
# ---------------------------------------------------------------------------

_PREMIUM_KEYWORDS = [
    "maldives", "switzerland", "swiss", "japan", "tokyo", "kyoto", "osaka",
    "dubai", "abu dhabi", "uae", "singapore", "iceland", "norway", "sweden",
    "denmark", "paris", "france", "italy", "venice", "rome", "london", "uk",
    "united kingdom", "usa", "united states", "new york", "california",
    "australia", "sydney", "new zealand", "seychelles", "mauritius",
    "monaco", "hong kong", "canada", "germany", "netherlands", "amsterdam",
]

_MODERATE_KEYWORDS = [
    "thailand", "bangkok", "phuket", "bali", "indonesia", "turkey",
    "istanbul", "egypt", "georgia", "malaysia", "philippines", "greece",
    "spain", "portugal", "south africa", "morocco", "china", "south korea",
    "seoul", "russia", "azerbaijan", "jordan", "oman", "qatar",
]

_BUDGET_KEYWORDS = [
    "nepal", "bhutan", "sri lanka", "bangladesh", "vietnam", "cambodia",
    "laos", "myanmar", "india", "goa", "kerala", "himachal", "kashmir",
    "rajasthan", "andaman", "northeast india", "ladakh", "uttarakhand",
]

_DEFAULT_TIER = "moderate"


def resolve_destination_tier(city: str | None, country: str | None) -> str:
    """Hand-authored destination -> cost tier ('budget' | 'moderate' | 'premium').
    Keyword substring match against city/country; defaults to 'moderate' when
    the destination isn't recognised (safer than assuming cheap or assuming
    expensive for an unknown place)."""
    haystack = f"{city or ''} {country or ''}".lower()
    if not haystack.strip():
        return _DEFAULT_TIER
    if any(k in haystack for k in _PREMIUM_KEYWORDS):
        return "premium"
    if any(k in haystack for k in _BUDGET_KEYWORDS):
        return "budget"
    if any(k in haystack for k in _MODERATE_KEYWORDS):
        return "moderate"
    return _DEFAULT_TIER


# ---------------------------------------------------------------------------
# Peak season detection (hand-authored, generic Indian-traveller calendar +
# a few destination-specific overrides where the "peak" window differs
# meaningfully from the generic Indian-holiday calendar).
# ---------------------------------------------------------------------------

_GENERIC_PEAK_MONTHS = {4, 5, 6, 10, 12, 1}  # summer + Diwali + winter holidays

_DESTINATION_PEAK_MONTHS: dict[str, set[int]] = {
    "maldives": {12, 1, 2, 3},
    "switzerland": {6, 7, 8, 12, 1},
    "swiss": {6, 7, 8, 12, 1},
    "japan": {3, 4, 10, 11},
    "europe": {6, 7, 8},
    "france": {6, 7, 8},
    "italy": {6, 7, 8},
    "thailand": {12, 1, 2},
    "bali": {7, 8, 12, 1},
    "dubai": {11, 12, 1, 2, 3},
    "uae": {11, 12, 1, 2, 3},
}


def is_peak_season(city: str | None, country: str | None, start_date: str | None) -> bool | None:
    """Returns True/False if a month is known, else None (unknown -> caller
    should not apply a season multiplier and should flag the assumption)."""
    if not start_date:
        return None
    try:
        month = date.fromisoformat(start_date[:10]).month
    except (ValueError, TypeError):
        return None

    haystack = f"{city or ''} {country or ''}".lower()
    for key, months in _DESTINATION_PEAK_MONTHS.items():
        if key in haystack:
            return month in months
    return month in _GENERIC_PEAK_MONTHS


# ---------------------------------------------------------------------------
# Bare-minimum per-person cost matrix: [destination_tier][traveller_level].
# flight_roundtrip_pp is one-time per traveller; stay_per_night_pp and
# food_per_day_pp are daily rates. INR, hand-authored (free-tools-only —
# no live pricing API), deliberately conservative "bare minimum" figures
# (e.g. shared double-occupancy budget-to-mid stay, not resort pricing).
# ---------------------------------------------------------------------------

_COST_MATRIX: dict[str, dict[str, dict[str, int]]] = {
    "budget": {
        "economical": {"flight_roundtrip_pp": 8000,  "stay_per_night_pp": 1000, "food_per_day_pp": 500},
        "mid_range":  {"flight_roundtrip_pp": 10000, "stay_per_night_pp": 2000, "food_per_day_pp": 800},
        "premium":    {"flight_roundtrip_pp": 14000, "stay_per_night_pp": 3500, "food_per_day_pp": 1300},
    },
    "moderate": {
        "economical": {"flight_roundtrip_pp": 15000, "stay_per_night_pp": 2000, "food_per_day_pp": 700},
        "mid_range":  {"flight_roundtrip_pp": 20000, "stay_per_night_pp": 3500, "food_per_day_pp": 1200},
        "premium":    {"flight_roundtrip_pp": 28000, "stay_per_night_pp": 6000, "food_per_day_pp": 2000},
    },
    "premium": {
        "economical": {"flight_roundtrip_pp": 28000, "stay_per_night_pp": 4000,  "food_per_day_pp": 1200},
        "mid_range":  {"flight_roundtrip_pp": 38000, "stay_per_night_pp": 8000,  "food_per_day_pp": 2000},
        "premium":    {"flight_roundtrip_pp": 55000, "stay_per_night_pp": 15000, "food_per_day_pp": 3500},
    },
}

_TIER_ORDER = {"budget": 0, "moderate": 1, "premium": 2}
_PEAK_SEASON_MULTIPLIER = 1.25  # applied to flight + stay only, not food

# Domestic-India trips are much cheaper than the "budget" international
# tier above (no international flight, no visa/forex overhead) — halve the
# flight component when scope is domestic.
_DOMESTIC_FLIGHT_DISCOUNT = 0.5


ECONOMICAL_KEYWORDS = ["economical", "budget", "cheap", "affordable", "backpack", "shoestring", "low cost", "low-cost", "save money", "frugal", "no frills", "bare minimum", "economy"]
PREMIUM_KEYWORDS = ["premium", "luxur", "splurge", "high-end", "high end", "five star", "5 star", "indulgent", "lavish", "no expense", "opulent", "upscale", "posh", "fancier", "top-notch", "top notch"]
# NOTE: "luxur" (not "luxury") is intentional — it substring-matches "luxury",
# "luxurious", and "luxuriously" in one go instead of missing common word
# forms the user actually types (this was a real bug: "a bit more luxurious
# stay" wasn't recognised as a premium signal because only the exact word
# "luxury" was in the list).


def parse_traveller_level(text: str | None) -> str | None:
    """Best-effort keyword parse of the user's own words for their desired
    spending level. Returns None if ambiguous (caller defaults to 'mid_range'
    but should treat it as a soft assumption, not a hard fact)."""
    if not text:
        return None
    lowered = text.lower()
    if any(k in lowered for k in PREMIUM_KEYWORDS):
        return "premium"
    if any(k in lowered for k in ECONOMICAL_KEYWORDS):
        return "economical"
    return None


def _group_headcount(group: dict[str, Any] | None) -> tuple[int, int, int, int]:
    """Returns (adults, kids, seniors, infants) from a group dict, tolerant of
    missing/partial data. Kids may be a list of ages or a list of {"age": n}."""
    group = group or {}
    adults = int(group.get("adults") or 0)
    seniors = int(group.get("seniors") or 0)
    infants = int(group.get("infants") or 0)
    kids_raw = group.get("kids") or []
    kids = len(kids_raw) if isinstance(kids_raw, list) else int(kids_raw or 0)
    return adults, kids, seniors, infants


def _duration_days(dates: dict[str, Any] | None) -> tuple[int, bool]:
    """Returns (duration_days, is_assumed). Falls back to a 5-day assumption
    when duration truly cannot be determined."""
    dates = dates or {}
    if dates.get("duration_days"):
        return int(dates["duration_days"]), False
    start, end = dates.get("start"), dates.get("end")
    if start and end:
        try:
            d = (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days + 1
            if d > 0:
                return d, False
        except (ValueError, TypeError):
            pass
    return 5, True


def estimate_bare_minimum_budget(trip_config: dict[str, Any], hint_text: str | None = None) -> dict[str, Any] | None:
    """Computes a bare-minimum (flights + stay + food) budget estimate.

    Returns None if group size is unknown (0 adults and 0 of everything else)
    — the caller should ask for group composition before quoting a number
    rather than falling back to a 1-person default, since guessing headcount
    silently is exactly the bug being fixed.

    `hint_text` is the user's own latest message, used only to detect an
    explicit "economical"/"premium" preference; never required.
    """
    group = trip_config.get("group") or {}
    adults, kids, seniors, infants = _group_headcount(group)
    total_known_people = adults + kids + seniors + infants
    if total_known_people == 0:
        return None  # caller must ask for group size first

    destination = trip_config.get("destination") or {}
    city = destination.get("city")
    country = destination.get("country")
    scope = trip_config.get("scope", "international")

    tier = resolve_destination_tier(city, country)
    traveller_level = parse_traveller_level(hint_text) or "mid_range"
    level_assumed = parse_traveller_level(hint_text) is None

    duration_days, duration_assumed = _duration_days(trip_config.get("dates"))
    nights = max(1, duration_days - 1)

    peak = is_peak_season(city, country, (trip_config.get("dates") or {}).get("start"))
    season_multiplier = _PEAK_SEASON_MULTIPLIER if peak else 1.0

    rates = _COST_MATRIX[tier][traveller_level]
    flight_pp = rates["flight_roundtrip_pp"] * season_multiplier
    if scope == "domestic":
        flight_pp *= _DOMESTIC_FLIGHT_DISCOUNT
    stay_pp_per_night = rates["stay_per_night_pp"] * season_multiplier
    food_pp_per_day = rates["food_per_day_pp"]

    # Already-booked flights/accommodation (⭐ user explicitly told Anya they've
    # already paid for these): use the user's REAL total instead of our
    # heuristic estimate for that component. That spend is a sunk cost, not
    # part of the "budget you still need" going forward, so it's reported
    # separately and excluded from `total_inr`/`per_person_inr` below.
    prebooked_flights = trip_config.get("prebooked_flights_inr")
    prebooked_accommodation = trip_config.get("prebooked_accommodation_inr")

    # Per-traveller-type cost weighting (bare-minimum, conservative):
    #   adults/seniors: full cost | kids (2-11): ~65% | infants: flight only, ~10%
    def _traveller_total(count: int, flight_share: float, daily_share: float) -> float:
        if count <= 0:
            return 0.0
        flight = flight_pp * flight_share
        stay = stay_pp_per_night * nights * daily_share
        food = food_pp_per_day * duration_days * daily_share
        return count * (flight + stay + food)

    flight_breakdown = round(
        flight_pp * (adults + seniors) + flight_pp * 0.75 * kids + flight_pp * 0.10 * infants, -2
    )
    stay_breakdown = round(
        stay_pp_per_night * nights * (adults + seniors + kids * 0.65 + infants * 0.15), -2
    )
    food_breakdown = round(
        food_pp_per_day * duration_days * (adults + seniors + kids * 0.65 + infants * 0.15), -2
    )

    # Swap in the user's real already-paid amounts where given, instead of
    # our heuristic guess for that component.
    flights_component = int(prebooked_flights) if prebooked_flights is not None else int(flight_breakdown)
    stay_component = int(prebooked_accommodation) if prebooked_accommodation is not None else int(stay_breakdown)
    food_component = int(food_breakdown)

    total = round(flights_component + stay_component + food_component, -2)
    per_person = round(total / total_known_people, -2)

    return {
        "total_inr": int(total),
        "per_person_inr": int(per_person),
        "breakdown": {
            "flights_inr": flights_component,
            "stay_inr": stay_component,
            "food_inr": food_component,
        },
        "destination_tier": tier,
        "traveller_level": traveller_level,
        "traveller_level_assumed": level_assumed,
        "duration_days": duration_days,
        "duration_assumed": duration_assumed,
        "peak_season": peak,
        "headcount": total_known_people,
        "flights_prebooked": prebooked_flights is not None,
        "accommodation_prebooked": prebooked_accommodation is not None,
    }


def budget_estimate_prompt_hint(trip_config: dict[str, Any], hint_text: str | None = None) -> str:
    """Renders either (a) an instruction to ask for group size first, or
    (b) the computed estimate the LLM should present verbatim (in its own
    words), formatted for direct interpolation into the wizard system prompt.
    Best-effort — returns an empty string on any failure so a bug here never
    blocks the conversation."""
    try:
        estimate = estimate_bare_minimum_budget(trip_config, hint_text)
    except Exception:
        return ""

    if estimate is None:
        return (
            "BUDGET RECOMMENDATION GUIDANCE: The user wants you to suggest/recommend a budget, "
            "but group size (who's travelling) is not yet known. Do NOT quote any number yet — "
            "ask for group composition first (e.g. 'Just me', 'Me + partner', 'Family with kids', "
            "'Group of friends'), THEN a follow-up turn will give you a real computed estimate to use."
        )

    b = estimate["breakdown"]
    assumptions = []
    if estimate["duration_assumed"]:
        assumptions.append(f"trip length assumed at {estimate['duration_days']} days (not yet confirmed)")
    if estimate["traveller_level_assumed"]:
        assumptions.append("assumed a mid-range comfort level (user didn't specify economical/premium)")
    if estimate["peak_season"] is None:
        assumptions.append("travel month unknown, so no peak-season adjustment applied")
    elif estimate["peak_season"]:
        assumptions.append("peak season for this destination — flights/stay skewed ~25% higher")
    if estimate["flights_prebooked"]:
        assumptions.append("using the user's real already-booked flight cost instead of an estimate")
    if estimate["accommodation_prebooked"]:
        assumptions.append("using the user's real already-booked accommodation cost instead of an estimate")
    assumptions_text = ("; ".join(assumptions) + ".") if assumptions else ""

    prebooked_note = (
        "Note: if the user mentions they've ALREADY BOOKED flights or accommodation, ask for the actual "
        "amount they paid (do not guess) and record it as prebooked_flights_inr / prebooked_accommodation_inr "
        "in config_patch — the estimate above will then use their real figures for that component instead of "
        "a heuristic guess.\n"
    )

    return (
        "BUDGET RECOMMENDATION GUIDANCE: Use this computed bare-minimum estimate (flights + stay + food "
        "only — local transport/activities/shopping are extra) instead of inventing a number yourself:\n"
        f"  Total for {estimate['headcount']} traveller(s), {estimate['duration_days']} days: "
        f"₹{estimate['total_inr']:,} (₹{estimate['per_person_inr']:,} per person)\n"
        f"  Breakdown — flights: ₹{b['flights_inr']:,} | stay: ₹{b['stay_inr']:,} | food: ₹{b['food_inr']:,}\n"
        f"  Destination cost tier: {estimate['destination_tier']} | comfort level used: {estimate['traveller_level']}\n"
        f"  {assumptions_text}\n"
        + prebooked_note +
        "Present this naturally in your own words, ALWAYS stating both the total AND the per-person figure, "
        "and mention it covers flights + stay + food as a bare minimum (activities/shopping/local transport "
        "are extra). If any assumption above is a guess, mention it briefly so the user can correct it."
    )

