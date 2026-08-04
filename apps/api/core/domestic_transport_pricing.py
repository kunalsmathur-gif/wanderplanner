"""India-domestic rail/bus/cab price alternative to flights.

Parallel to `core/distance_pricing.py`'s flight bands, but scoped ONLY to
domestic (India-internal) routes — international routes have no rail/bus
alternative worth modelling here and stay flight-only. Used by
`core/budget_estimator.py` to compute a `cheaper_alternative` call-out when
train/bus is meaningfully cheaper than flying, per the Kaggle-pricing-plan
Workstream A scope.

Confidence: LOW-MEDIUM. No official downloadable per-km fare table exists
for Indian Railways — CRIS/PRS uses a private telescopic distance-slab
lookup that isn't published. The bands below are back-calculated
approximations derived from real seat61.com fare examples (the same
sourcing approach recorded in `docs/NEXT_SESSION_TODO.md`'s 2026-07-21
domestic-pricing research), accurate to roughly ±15-20% — enough for a
"you could save money taking the train" nudge, not a fare quote. Validate
against `erail.in/train-fare` before trusting these for anything more
precise than a rough comparison.

Known HIGH-confidence surcharges NOT modelled here (would need per-train
data this module doesn't have): reservation charges, superfast surcharge,
5% GST on AC classes only, Tatkal premium (10-30% of base fare),
train-type multipliers (Rajdhani/Shatabdi run a flexi-fare ladder above
plain Mail/Express fares). The bands below are deliberately for a
plain-Express-class fare, which undershoots premium train types — biasing
the comparison in the "train is cheaper" direction is the safer failure
mode for a savings call-out (we'd rather undersell than oversell the
alternative), but this means the estimate is a floor, not an average.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Rail fare bands: ₹/km slabs by class tier, applied as a flat per-km rate
# below `_TELESCOPIC_TAPER_KM`, then tapered down for longer distances —
# Indian Railways' real telescopic slabs give a *lower* effective ₹/km the
# longer the journey (a fixed per-journey overhead is amortised over more
# km), which a single flat rate would misrepresent for, e.g., Delhi->Chennai
# (~2180km) vs. Delhi->Agra (~200km).
# ---------------------------------------------------------------------------

# class_tier keys match core/budget_estimator.py's traveller_level vocabulary
# ("economical" | "mid_range" | "premium") so the two modules compose
# without a translation layer. Mapped to real Indian Railways classes:
#   economical -> Sleeper Class (SL), non-AC
#   mid_range  -> AC 3-Tier (3AC)
#   premium    -> AC 2-Tier (2AC)
# AC 1st Class (1AC) is deliberately not modelled — rare availability, and
# its fare is closer to a discounted flight than a "cheaper alternative".
RAIL_RATE_PER_KM_INR: dict[str, float] = {
    "economical": 0.55,   # Sleeper Class
    "mid_range": 1.45,    # AC 3-Tier
    "premium": 2.10,      # AC 2-Tier
}

# Beyond this distance, Indian Railways' telescopic slabs give a materially
# lower effective ₹/km than short-haul journeys (fixed overhead amortised
# over more km) — apply a flat discount to the per-km rate for the portion
# of the journey past this point, rather than a single flat rate that would
# overstate long-haul fares.
_TELESCOPIC_TAPER_KM = 500
_TELESCOPIC_TAPER_DISCOUNT = 0.75  # per-km rate beyond the taper point is 75% of the base rate

# A short minimum fare floor — no real Indian Railways journey costs less
# than this regardless of distance (station/reservation overhead), so a
# very short domestic hop shouldn't price out near-zero.
_RAIL_MINIMUM_FARE_INR = 150


def _rail_fare_inr(distance_km: float, class_tier: str) -> int:
    rate = RAIL_RATE_PER_KM_INR[class_tier]
    if distance_km <= _TELESCOPIC_TAPER_KM:
        fare = distance_km * rate
    else:
        fare = (
            _TELESCOPIC_TAPER_KM * rate
            + (distance_km - _TELESCOPIC_TAPER_KM) * rate * _TELESCOPIC_TAPER_DISCOUNT
        )
    # `round(x, -1)` on a float returns a float, so `max(int, float)` widens the
    # whole expression to float and breaks the `-> int` contract these fares are
    # consumed under (they land in int-typed INR fields). The value is already a
    # whole multiple of 10 by then, so `int()` is exact, never a truncation.
    return int(max(_RAIL_MINIMUM_FARE_INR, round(fare, -1)))  # round to nearest 10


# ---------------------------------------------------------------------------
# Bus fare bands: intercity AC Volvo/sleeper-coach ₹/km slabs. Simpler than
# rail — no telescopic tapering (private bus operators price closer to
# flat-rate-per-km than the state-subsidised rail network does), but bus
# becomes an impractical option well before flight distances, so this
# module doesn't extrapolate it past `_BUS_MAX_KM`.
# ---------------------------------------------------------------------------

BUS_RATE_PER_KM_INR: dict[str, float] = {
    "economical": 1.10,   # non-AC seater/sleeper
    "mid_range": 1.75,    # AC seater
    "premium": 2.40,      # AC sleeper (Volvo-class)
}

_BUS_MINIMUM_FARE_INR = 200
# Bus stops being a realistic alternative well past this distance (multi-day
# journeys aren't a genuine substitute for a domestic flight) — treat it as
# unavailable rather than extrapolate an implausible fare.
_BUS_MAX_KM = 1200


def _bus_fare_inr(distance_km: float, class_tier: str) -> int | None:
    if distance_km > _BUS_MAX_KM:
        return None
    rate = BUS_RATE_PER_KM_INR[class_tier]
    return int(max(_BUS_MINIMUM_FARE_INR, round(distance_km * rate, -1)))


# ---------------------------------------------------------------------------
# Cab: only offered for short hops, where door-to-door convenience can
# plausibly compete with a train/flight/bus booking at all.
# ---------------------------------------------------------------------------

CAB_MAX_KM = 150
_CAB_RATE_PER_KM_INR = 14.0  # round-trip-agnostic outstation one-way cab rate, mid-range
_CAB_MINIMUM_FARE_INR = 800


def _cab_fare_inr(distance_km: float) -> int | None:
    if distance_km > CAB_MAX_KM:
        return None
    return int(max(_CAB_MINIMUM_FARE_INR, round(distance_km * _CAB_RATE_PER_KM_INR, -1)))


def estimate_domestic_alternative(distance_km: float, class_tier: str) -> dict[str, int | None]:
    """Rail/bus/cab one-way fare estimates (INR per passenger) for a
    domestic (India-internal) route of `distance_km`, at `class_tier`
    ("economical" | "mid_range" | "premium" — same vocabulary as
    core/budget_estimator.py's traveller_level).

    Returns a dict with `rail_inr` (always present), `bus_inr` (None beyond
    `_BUS_MAX_KM`), and `cab_inr` (None beyond `CAB_MAX_KM`) — a None value
    means "not a realistic option at this distance", not "unknown"; callers
    should treat it as excluded from any comparison, not missing data.
    """
    if class_tier not in RAIL_RATE_PER_KM_INR:
        raise ValueError(f"Unknown class_tier: {class_tier!r} (expected economical/mid_range/premium)")
    if distance_km <= 0:
        raise ValueError(f"distance_km must be positive, got {distance_km!r}")

    return {
        "rail_inr": _rail_fare_inr(distance_km, class_tier),
        "bus_inr": _bus_fare_inr(distance_km, class_tier),
        "cab_inr": _cab_fare_inr(distance_km),
    }
