"""Shared free-tools distance-based flight-fare heuristic.

Used by both `core/cost_grounding.py` (feasibility/itinerary prompts) and
`core/budget_estimator.py` (wizard-chat budget recommendation) so the two
budget-facing code paths agree on the same real-distance-based fare band
instead of drifting apart. See `cost_grounding.py`'s module docstring for
the full free-tools design rationale.
"""
from __future__ import annotations

import math

# (max_km, low_inr, high_inr) round-trip economy, per passenger, India-origin
# assumption. Bands are intentionally wide — this is a sanity-check range,
# not a quote.
#
# Recalibrated 2026-07-20 against a real fare data point: Bengaluru->Colombo
# (~750km, "near-neighbour" band) priced at a real ₹12,000 one-way + ₹15,000
# return = ₹27,000 round trip for Nov 2026 — the original band here
# (₹7,000-15,000) undershot that by ~2.4x. The near-neighbour band is
# recalibrated directly off this anchor (mid_range fraction ~0.5 now lands
# at ~₹21,000, premium ~0.9 lands at ~₹28,200 — bracketing the real fare).
# The short-domestic-hop band is nudged up modestly for the same general
# fare inflation. Note that short-haul South Asian routes (India<->Sri
# Lanka/Nepal/Bangladesh) are disproportionately pricey per km versus
# competitive long-haul corridors (India<->Gulf/Europe), due to far fewer
# carriers/frequencies — so do NOT rescale every band by the same ~2.4x
# ratio derived from this one near-neighbour anchor; that would overshoot
# the long-haul bands.
#
# Recalibrated again same day against a second real anchor:
# Bengaluru->London (~8000km, "long-haul" band) priced at a real ₹67,327
# round trip (MakeMyTrip, "Popular" sort, Aug 2026 — the original band here
# (₹32,000-65,000) undershot the midpoint by ~1.4x. Recalibrated via
# `scripts/recalibrate_pricing.py --band long_haul --round-trip-inr 67327`
# (mid_range fraction ~0.5 now lands almost exactly on the real fare).
# ultra_long_haul (already comfortably above the recalibrated long_haul
# band — no nudge needed to stay monotonic) is unchanged.
#
# Recalibrated a third time same day: Delhi->Goa (~1504km) at Christmas/
# New Year peak pricing (MakeMyTrip, Dec 2026) priced at a real ₹18,157
# round trip cheapest — this is a *domestic* route that lands just 4km
# past the near-neighbour cutoff (1500km) and so falls into the
# "regional international" band, but its real fare undershoots that
# band's old ₹20,000 low even at holiday-peak pricing. Rather than a
# full symmetric rescale (which would also drop the band's high end —
# used for genuinely pricier international regional routes like
# Bangkok/Dubai that this domestic anchor says nothing about), only the
# low end was nudged down to ₹12,105 (via
# `scripts/recalibrate_pricing.py --band regional --round-trip-inr 18157`,
# taking just the low value from its output). The high end (₹40,000)
# is left unchanged pending a real international-regional data point.
DISTANCE_BANDS: list[tuple[float, int, int]] = [
    (500, 5000, 11000),            # short domestic hop
    (1500, 12000, 30000),          # domestic / near-neighbour international
    (4000, 12105, 40000),          # regional international (SE Asia, Middle East) — low end nudged down: real anchor Delhi->Goa peak (Dec) ₹18,157 landed just over the near-neighbour cutoff (1504km) and undershot the old ₹20,000 low even at holiday-peak pricing; high end (genuine int'l routes like Bangkok/Dubai) left unchanged since this anchor is a domestic route, not evidence for the top of the band
    (8000, 44422, 90232),          # long-haul (Europe, East Asia) — real anchor: Bengaluru->London ₹67,327 (2026-07-20)
    (float("inf"), 55000, 110000),  # ultra-long-haul (Americas, Oceania)
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0  # Earth radius, km
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def distance_band_inr(km: float) -> tuple[int, int]:
    for max_km, low, high in DISTANCE_BANDS:
        if km <= max_km:
            return low, high
    return DISTANCE_BANDS[-1][1], DISTANCE_BANDS[-1][2]


def flight_band_inr(
    origin_lat: float | None, origin_lon: float | None, dest_lat: float | None, dest_lon: float | None
) -> tuple[int, int] | None:
    """Round-trip economy fare band (low, high) INR per passenger, or None if
    any coordinate is missing/zero (not yet geocoded)."""
    if not origin_lat or not origin_lon or not dest_lat or not dest_lon:
        return None
    km = haversine_km(origin_lat, origin_lon, dest_lat, dest_lon)
    return distance_band_inr(km)
