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
# fare inflation. The regional/long-haul/ultra-long-haul bands (no real
# anchor available yet) are nudged up just enough to preserve monotonic
# ordering against the recalibrated near-neighbour band — they are NOT
# independently verified against real fares and should be recalibrated the
# same way once a real data point turns up for one of them. Note that
# short-haul South Asian routes (India<->Sri Lanka/Nepal/Bangladesh) are
# disproportionately pricey per km versus competitive long-haul corridors
# (India<->Gulf/Europe), due to far fewer carriers/frequencies — so do NOT
# rescale every band by the same ~2.4x ratio derived from this one
# near-neighbour anchor; that would overshoot the long-haul bands.
DISTANCE_BANDS: list[tuple[float, int, int]] = [
    (500, 5000, 11000),            # short domestic hop
    (1500, 12000, 30000),          # domestic / near-neighbour international
    (4000, 20000, 40000),          # regional international (SE Asia, Middle East)
    (8000, 32000, 65000),          # long-haul (Europe, East Asia)
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
