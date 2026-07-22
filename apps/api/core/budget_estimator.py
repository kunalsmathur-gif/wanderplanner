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

The estimate deliberately requires group size AND departure city to be known
before `budget_estimate_prompt_hint()` will hand the LLM a number — if either
is missing it returns clarifying-question guidance instead, so the LLM asks
before it quotes. Two UX bugs are fixed this way: Anya used to quote a flat
40,000 INR "budget trip" figure before even knowing headcount, and separately
used one hand-authored flight number per destination tier regardless of
departure city (a Delhi-Colombo and a Chennai-Colombo trip got the exact same
"flight" line, wildly wrong for both). Once origin+destination are geocoded
(lat/lon available), the flight component switches to the real-distance band
from `core/distance_pricing.py` (shared with `core/cost_grounding.py`)
instead of the flat per-tier number — see `flight_distance_based` in the
returned dict.

Stay and food work the same way, one level further: `_grounded_or_flat()`
tries a real per-destination figure first — the median of community-reported
nightly-rate/daily-spend mentions pulled from the app's existing free RAG
collections (Reddit/Wikivoyage/YouTube comments, via `core/cost_grounding.py`
+ `core/price_extraction.py`'s deterministic regex extraction, NOT an LLM
call — reintroducing LLM guessing here would recreate the exact problem this
module exists to avoid) — and only falls back to the hand-authored flat
_COST_MATRIX number when that comes up empty. As of 2026-07-20 the Reddit/
Wikivoyage Qdrant collections are near-empty in production, so this falls
back further for most destinations today; the plumbing is in place for when
ingestion improves. See `stay_community_based` / `food_community_based` in
the returned dict.

For stay specifically, there's one more fallback rung between community
grounding and the flat _COST_MATRIX number: `core/airbnb_pricing.py`'s small,
manually-seeded per-city lookup of real Inside Airbnb (CC BY 4.0) hotel-
equivalent rates, for destinations where Wikivoyage has no usable inline
hotel-pricing data but Inside Airbnb has real listing data (e.g. Istanbul).
See `stay_airbnb_fallback_used` in the returned dict. Separately (and
compatibly — the two can combine), if the user explicitly asks for an
Airbnb/vacation-rental stay (`wants_airbnb_stay()`), whatever stay rate was
resolved above gets discounted by `_AIRBNB_STAY_DISCOUNT_MULTIPLIER` to
approximate self-catering pricing instead of a hotel room — see
`stay_airbnb_based` in the returned dict.

⚠️ PRE-COMMERCIAL-ONLY DATA SOURCES — remove/re-source before commercial
launch: this project is not yet in a commercial phase (no paid product, no
revenue), so `_COST_MATRIX` currently cites two sources whose Terms of
Service prohibit *commercial* reuse of their data without a paid license:
  - **Numbeo** (numbeo.com) — premium-tier `food_per_day_pp` (see that
    row's docstring below for the exact figures/citations).
  - **budgetyourtrip.com** — `stay_per_night_pp` for moderate/premium tiers
    (see that row's docstring below).
Both are fine to use pre-commercial (this is explicitly a non-commercial,
free-tools research/build phase) but MUST be removed or re-sourced from a
compliant alternative (Wikivoyage CC BY-SA 3.0 and Inside Airbnb CC BY 4.0
are already wired in alongside them as compliant cross-checks/fallbacks —
see each row's docstring) before any commercial launch. Tracked as a
pre-launch checklist item in `docs/NEXT_SESSION_TODO.md`.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from core.airbnb_pricing import airbnb_hotel_equivalent_pp_inr
from core.cost_grounding import community_median_price_inr
from core.distance_pricing import flight_band_inr
from core.price_extraction import FOOD_CONTEXT_KEYWORDS, STAY_CONTEXT_KEYWORDS

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
# flight_roundtrip_pp is one-time per traveller (used only when the real
# distance band above isn't available yet); stay_per_night_pp and
# food_per_day_pp are daily rates, used only when community grounding above
# comes up empty (currently the common case). INR, hand-authored (free-tools-
# only — no live pricing API), deliberately conservative "bare minimum"
# figures (e.g. shared double-occupancy budget-to-mid stay, not resort
# pricing).
#
# food_per_day_pp recalibrated 2026-07-20 against real research for Sri
# Lanka (budget tier): mid-range dining runs ~$20-25/person/day (₹1,660-
# 2,075) — cafe/curry spots at $5-10/meal, beach cafes $10-20/meal — while
# the original figure here (₹800/day) was undershooting that by ~2-2.5x, in
# the same direction as the flight bug. The budget-tier mid_range cell is the
# one hard anchor; economical/premium within that tier and the other two
# destination tiers are scaled proportionally (not independently verified —
# recalibrate the same way once a real data point turns up for one of them).
# stay_per_night_pp was checked against the same research (~$50/night
# Colombo double room, ~₹2,075/person) and found close to the existing
# ₹2,000 mid_range figure — left unchanged rather than "fixed" without
# evidence it was actually wrong.
#
# food_per_day_pp for the "moderate" tier spot-checked 2026-07-21 against
# real Numbeo cost-of-living data for Bangkok (jul-2026 snapshot,
# numbeo.com/cost-of-living/in/Bangkok): a day of inexpensive breakfast
# (฿120) + inexpensive lunch (฿120) + a mid-range dinner (per-person half of
# the "meal for two" figure, ฿600) + one cappuccino (฿96) = ฿936/day,
# converted at THB/INR ≈ 2.42 (derived from `core/config.py`'s
# usd_to_inr_rate=87 and ~36 THB/USD) = ~₹2,265/day — within ~3% of the
# existing ₹2,200 mid_range figure and ~₹1,137 for the economical-tier
# equivalent (2 inexpensive meals + fast food) vs. the existing ₹1,200.
# Both already-close — left unchanged (same "verified, not broken" call as
# the Sri Lanka stay figure above).
#
# food_per_day_pp for the "premium" tier RECALIBRATED 2026-07-21 against
# real Numbeo cost-of-living data for Paris (same jul-2026 snapshot,
# numbeo.com/cost-of-living/in/Paris), converted at EUR/INR ≈ 93:
#   - economical (inexpensive breakfast €15.50 + inexpensive lunch €15.50 +
#     a fast-food dinner €12.00 + bottled water €2.64 = €45.64/day) → ₹4,245
#   - mid_range (inexpensive breakfast €15.50 + inexpensive lunch €15.50 +
#     a mid-range dinner, per-person half of the "meal for two" figure
#     €35.00 + one cappuccino €4.39 = €70.39/day) → ₹6,546
#   - premium (top-of-range inexpensive meals €22+€22 + top-of-range
#     mid-range dinner €50 pp + top-of-range cappuccino €6 = €100/day) → ₹9,300
# ⚠️ Numbeo's ToS requires a paid commercial "Data License" for use beyond
# personal/academic purposes — fine for this project's current pre-commercial
# phase, but MUST be removed/re-sourced before commercial launch (see the
# module-level "PRE-COMMERCIAL-ONLY DATA SOURCES" note above and
# `docs/NEXT_SESSION_TODO.md`).
#
# Cross-checked 2026-07-22 against Wikivoyage (CC BY-SA 3.0, compliant)
# "Eat" section listings, which use their own Budget/Mid-range/Splurge
# categorization — a live, course-matched comparison against fresh Numbeo
# data (economical €44.55 / mid_range €69.45 / premium €100.00, same
# formula shape as above) found Wikivoyage landing close for Paris
# (economical €39.50, ~13% lower; mid_range €64.00, ~9% lower; premium
# €87.00, ~13% lower — ratios 1.13x/1.09x/1.15x). Testing that ~1.12x
# Paris-derived multiplier against two more cities showed it does **not**
# generalize: Bangkok's ratios came out 2.37x/1.53x/1.30x (Wikivoyage's
# "Budget" listings there are genuine street-food/night-market stalls,
# 30-60 baht, vs. Numbeo's "inexpensive restaurant" figure which reflects
# an actual sit-down cheap restaurant — different real-world categories
# that both happen to get called "budget"), and Tokyo/Shinjuku's Wikivoyage
# listings were too sparse/format-inconsistent (a single noodle dish vs. an
# all-you-can-eat buffet vs. several listings with no price at all) to even
# compute a reliable ratio. Conclusion: no single global Wikivoyage->Numbeo
# multiplier is defensible — a per-city multiplier, derived fresh each time
# (same spirit as the stay_per_night_pp cross-check above, which only ever
# claimed to be Paris-specific), would be the correct approach if Numbeo
# ever needs to be dropped, not a blanket conversion factor. Not applied to
# this table — Numbeo's own figures are kept pre-commercial (see ToS note
# above).
# All three cells were undershooting by ~1.4-2.2x (worse at the lower
# spending styles, same direction/shape as the Sri Lanka food-tier bug) —
# unlike that fix, this one has an independently-sourced real number for
# every cell in the row (not one anchor + proportional scaling), so all
# three are applied directly. stay_per_night_pp for this tier is NOT
# recalibrated this pass — Numbeo doesn't track hotel nightly rates and no
# free, non-JS-rendered hotel-pricing source was found; left as the existing
# hand-authored figure pending a real anchor (see
# `scripts/recalibrate_pricing.py`'s docstring for candidate sources).
#
# stay_per_night_pp for "moderate" and "premium" tiers RECALIBRATED
# 2026-07-21 (later) against real budgetyourtrip.com "average traveler"
# hotel-spend figures, converted at USD/INR = 83:
#   - Bangkok (moderate/mid_range anchor): $96/day → ₹7,968
#   - Paris (premium/mid_range anchor): $350/day → ₹29,050
# ⚠️ budgetyourtrip.com's ToS prohibits this kind of commercial reuse
# without a paid license — fine for this project's current pre-commercial
# phase (no paid product/revenue yet), but MUST be removed/re-sourced
# before commercial launch (see the module-level "PRE-COMMERCIAL-ONLY DATA
# SOURCES" note above and `docs/NEXT_SESSION_TODO.md`).
#
# Cross-checked 2026-07-22 against a fully compliant, commercial-use-cleared
# source — Wikivoyage (CC BY-SA 3.0, already the license basis for this
# project's `wiki` RAG collection) — to see how far a licensing-safe
# reconstruction would land, in case budgetyourtrip.com ever needs to be
# dropped again:
#   Step 1 — real per-night hotel rates scraped from Wikivoyage district
#   "Sleep" sections (a compliant source, unlike Booking.com/Skyscanner,
#   which are JS-rendered, or Numbeo, which doesn't track hotel rates):
#     - Bangkok/Sukhumvit mid-range hotels: ~₹2,570/night/pp (THB/INR≈2.42)
#     - Paris/1st arrondissement mid-range hotels: ~₹6,740/night/pp (EUR/INR≈93)
#   Step 2 — a multiplier accounting for the gap between a nominal listed
#   room rate and what travellers actually report spending (taxes/fees not
#   in the listed rate, occasional upgrades, selection bias toward
#   higher-visibility properties), derived by comparing the Wikivoyage
#   figures above against the budgetyourtrip.com figures above:
#     - moderate tier: 3.08x (avg of two independently-checked moderate-
#       tier cities, Bangkok 3.10x and Athens 3.06x — the two agreeing this
#       closely is the reason this multiplier is trusted for the whole tier)
#     - premium tier: 4.31x (Paris only — single anchor, needs a second
#       independent premium-tier city before being fully trusted)
#   Step 3 — Wikivoyage figure × multiplier, rounded: Bangkok ₹2,570 × 3.08
#   → ₹7,916; Paris ₹6,740 × 4.31 → ₹29,049 — within ~1 INR of the
#   budgetyourtrip.com figures actually stored in the table below, i.e. the
#   two independent sources corroborate each other closely. **The table
#   below uses the direct budgetyourtrip.com figures** (₹7,968/₹29,050),
#   since that source is allowed pre-commercial and is the more direct
#   anchor; swap to the Wikivoyage-reconstructed figures (₹7,916/₹29,049,
#   functionally identical) if budgetyourtrip.com needs to be dropped later.
# Both anchors are still a mid_range proxy, not separately sourced per
# spending style — the script's usual "nudge neighbours just enough to
# preserve monotonicity" mechanism keeps economical <= mid_range <= premium
# (both spending-style-within-tier and same-style-across-tier) consistent:
# moderate/premium nudged to 9,163; premium/premium nudged to 33,408.
# economical-tier figures for both rows are untouched — no real anchor for
# that style yet. Treat the exact numbers as a first real anchor, not
# gospel, and keep sourcing more independent anchors (ideally per spending
# style, and a second premium-tier city, not just mid_range) as they turn up.
# ---------------------------------------------------------------------------

_COST_MATRIX: dict[str, dict[str, dict[str, int]]] = {
    "budget": {
        "economical": {"flight_roundtrip_pp": 8000,  "stay_per_night_pp": 1000, "food_per_day_pp": 900},
        "mid_range":  {"flight_roundtrip_pp": 10000, "stay_per_night_pp": 2000, "food_per_day_pp": 1800},
        "premium":    {"flight_roundtrip_pp": 14000, "stay_per_night_pp": 3500, "food_per_day_pp": 3200},
    },
    "moderate": {
        "economical": {"flight_roundtrip_pp": 15000, "stay_per_night_pp": 2000, "food_per_day_pp": 1200},
        "mid_range":  {"flight_roundtrip_pp": 20000, "stay_per_night_pp": 7968, "food_per_day_pp": 2200},
        "premium":    {"flight_roundtrip_pp": 28000, "stay_per_night_pp": 9163, "food_per_day_pp": 3800},
    },
    "premium": {
        "economical": {"flight_roundtrip_pp": 28000, "stay_per_night_pp": 4000,  "food_per_day_pp": 4245},
        "mid_range":  {"flight_roundtrip_pp": 38000, "stay_per_night_pp": 29050, "food_per_day_pp": 6546},
        "premium":    {"flight_roundtrip_pp": 55000, "stay_per_night_pp": 33408, "food_per_day_pp": 9300},
    },
}

_TIER_ORDER = {"budget": 0, "moderate": 1, "premium": 2}

# ---------------------------------------------------------------------------
# Airbnb/vacation-rental stay discount, for travellers who explicitly ask for
# a self-catering/Airbnb stay instead of a hotel. Sourced 2026-07-22 from
# real Inside Airbnb "entire home/apt" listing data (CC BY 4.0 licensed,
# https://insideairbnb.com — commercial use permitted with attribution),
# NOT scraped from Airbnb.com itself:
#   - Bangkok: median ฿1,712/night whole apt (n=19,250 listings) → ₹2,071/pp
#     (÷2 for double occupancy) vs. this file's hotel mid_range rate of
#     ₹7,968/pp → ratio 0.260
#   - Paris: median €212/night whole apt (n=42,945 listings) → ₹9,858/pp
#     vs. this file's hotel mid_range rate of ₹29,050/pp → ratio 0.339
# Average of the two ratios ≈ 0.30, applied as a flat discount against
# whatever hotel-based stay rate would otherwise have been used (community-
# grounded or flat _COST_MATRIX). This is a rough, 2-city heuristic — entire-
# home Airbnb listings often sleep more than 2 people and span a much wider
# quality/location range than a curated hotel list, so treat this as
# directionally useful, not a precise per-city anchor.
_AIRBNB_STAY_DISCOUNT_MULTIPLIER = 0.30

_AIRBNB_KEYWORDS = ("airbnb", "air bnb", "air b&b", "vacation rental", "self-catering", "self catering")


def wants_airbnb_stay(text: str | None) -> bool:
    """Best-effort keyword parse of the user's own words for an explicit
    Airbnb/vacation-rental stay preference (as opposed to a hotel)."""
    if not text:
        return False
    lowered = text.lower()
    return any(k in lowered for k in _AIRBNB_KEYWORDS)
_PEAK_SEASON_MULTIPLIER = 1.25  # applied to flight + stay only, not food

# When origin+destination coordinates are known, the real-distance band from
# core.distance_pricing (shared with core/cost_grounding.py) replaces the flat
# _COST_MATRIX flight figure — traveller_level then picks where in that band
# to land, instead of selecting a whole separate hand-authored number.
_LEVEL_BAND_FRACTION = {"economical": 0.15, "mid_range": 0.5, "premium": 0.9}

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


# Sanity bounds for community-extracted stay/food amounts (INR) — a snippet
# match outside these ranges is almost certainly not actually a nightly rate
# / daily food spend and gets discarded by core.price_extraction.
_STAY_PP_BOUNDS = (300, 50_000)
_FOOD_PP_BOUNDS = (100, 10_000)


async def _grounded_or_flat(
    city: str | None,
    country: str | None,
    query_suffix: str,
    flat_default: float,
    bounds: tuple[float, float],
    context_keywords: frozenset[str] | None = None,
) -> tuple[float, bool]:
    """Real per-destination community-reported figure (INR) if the free RAG
    collections have enough signal for it, else the hand-authored flat
    default. Best-effort — a retrieval hiccup or empty corpus (the common
    case today, see core/cost_grounding.py) just falls back, never blocks
    the estimate."""
    dest_city = city or country
    if not dest_city:
        return flat_default, False
    try:
        grounded = await community_median_price_inr(
            dest_city, query_suffix, bounds[0], bounds[1], context_keywords=context_keywords
        )
    except Exception:
        grounded = None
    if grounded is not None:
        return grounded, True
    return flat_default, False


async def estimate_bare_minimum_budget(
    trip_config: dict[str, Any], hint_text: str | None = None
) -> dict[str, Any] | None:
    """Computes a bare-minimum (flights + stay + food) budget estimate.

    Returns None if group size is unknown (0 adults and 0 of everything else)
    — the caller should ask for group composition before quoting a number
    rather than falling back to a 1-person default, since guessing headcount
    silently is exactly the bug being fixed.

    `hint_text` is the user's own latest message, used only to detect an
    explicit "economical"/"premium" preference and/or an explicit Airbnb/
    vacation-rental stay preference (see `wants_airbnb_stay`); never required.
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

    origin = trip_config.get("origin") or {}
    band = flight_band_inr(origin.get("lat"), origin.get("lon"), destination.get("lat"), destination.get("lon"))
    if band:
        low, high = band
        frac = _LEVEL_BAND_FRACTION[traveller_level]
        flight_pp_base = low + (high - low) * frac
        flight_distance_based = True
    else:
        flight_pp_base = rates["flight_roundtrip_pp"]
        flight_distance_based = False

    flight_pp = flight_pp_base * season_multiplier
    if scope == "domestic":
        flight_pp *= _DOMESTIC_FLIGHT_DISCOUNT

    stay_pp_base, stay_community_based = await _grounded_or_flat(
        city, country, "hotel accommodation nightly rate per person", rates["stay_per_night_pp"], _STAY_PP_BOUNDS,
        context_keywords=STAY_CONTEXT_KEYWORDS,
    )
    stay_airbnb_fallback_used = False
    if not stay_community_based:
        airbnb_fallback_pp = airbnb_hotel_equivalent_pp_inr(city, country)
        if airbnb_fallback_pp is not None:
            stay_pp_base = airbnb_fallback_pp
            stay_airbnb_fallback_used = True
    airbnb_requested = wants_airbnb_stay(hint_text)
    if airbnb_requested:
        stay_pp_base = round(stay_pp_base * _AIRBNB_STAY_DISCOUNT_MULTIPLIER)
    food_pp_base, food_community_based = await _grounded_or_flat(
        city, country, "food meal daily cost per person", rates["food_per_day_pp"], _FOOD_PP_BOUNDS,
        context_keywords=FOOD_CONTEXT_KEYWORDS,
    )
    stay_pp_per_night = stay_pp_base * season_multiplier
    food_pp_per_day = food_pp_base

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
        "flight_distance_based": flight_distance_based,
        "origin_city": origin.get("city"),
        "stay_community_based": stay_community_based,
        "food_community_based": food_community_based,
        "stay_airbnb_based": airbnb_requested,
        "stay_airbnb_fallback_used": stay_airbnb_fallback_used,
    }


async def budget_estimate_prompt_hint(trip_config: dict[str, Any], hint_text: str | None = None) -> str:
    """Renders either (a) an instruction to ask for group size first, or
    (b) the computed estimate the LLM should present verbatim (in its own
    words), formatted for direct interpolation into the wizard system prompt.
    Best-effort — returns an empty string on any failure so a bug here never
    blocks the conversation."""
    try:
        estimate = await estimate_bare_minimum_budget(trip_config, hint_text)
    except Exception:
        return ""

    if estimate is None:
        return (
            "BUDGET RECOMMENDATION GUIDANCE: The user wants you to suggest/recommend a budget, "
            "but group size (who's travelling) is not yet known. Do NOT quote any number yet — "
            "ask for group composition first (e.g. 'Just me', 'Me + partner', 'Family with kids', "
            "'Group of friends'), THEN a follow-up turn will give you a real computed estimate to use."
        )

    # Flight cost varies hugely by departure city (a flat per-destination
    # number was the actual bug being fixed here — see budget_estimator.py's
    # module docstring). Skip this gate when the flight component is already
    # the user's real prebooked figure, since no flight estimate is needed then.
    if not estimate["origin_city"] and not estimate["flights_prebooked"]:
        return (
            "BUDGET RECOMMENDATION GUIDANCE: The user wants you to suggest/recommend a budget. Group size and "
            "destination are known, but their DEPARTURE CITY is not yet known — flight cost varies hugely by "
            "departure city, so do NOT quote any number yet. Ask which city they'll be flying from (e.g. "
            "'Which city will you be flying out of?'), THEN a follow-up turn will give you a real computed "
            "estimate to use."
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
    if not estimate["flight_distance_based"] and not estimate["flights_prebooked"]:
        assumptions.append(
            "couldn't pin down real flight distance for this departure city yet, so flights use a generic "
            "destination-tier estimate rather than a route-specific one"
        )
    if estimate["stay_airbnb_based"]:
        assumptions.append("stay cost estimated for an Airbnb/vacation-rental stay (user asked for one), not a hotel")
    elif estimate["stay_airbnb_fallback_used"]:
        assumptions.append("stay cost is a hotel-equivalent estimate derived from real Airbnb listing data for this destination")
    elif estimate["stay_community_based"]:
        assumptions.append("stay cost is grounded in real traveller-reported rates for this destination")
    if estimate["food_community_based"]:
        assumptions.append("food cost is grounded in real traveller-reported spend for this destination")
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

