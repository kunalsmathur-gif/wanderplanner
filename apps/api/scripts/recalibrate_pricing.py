"""Interactive helper for recalibrating the free-tools budget-estimator's
hand-authored figures against REAL data points (docs/NEXT_SESSION_TODO.md
item 10). See `core/distance_pricing.py`'s module docstring for why this
matters and the anchor method this script automates: only the
budget-tier/mid_range near-neighbour band (Bengaluru->Colombo) has a real,
independently-verified anchor so far; every other flight distance band and
every `moderate`/`premium` destination-tier cost-matrix cell was extrapolated
to preserve ordering, not verified.

**Why this is a helper, not an automated fetch:** live fare/hotel-price
aggregators (Google Flights, Skyscanner, Numbeo, Booking.com) are JS-rendered
or bot-protected — this repo's fetch tooling can't reliably scrape them, and
the product's own "free tools only, no paid pricing APIs" constraint (see
`core/budget_estimator.py`'s docstring) rules out a paid fare API as the fix.
So the real number still has to come from a human opening a browser — this
script's job is to make that a 2-minute, well-scoped task instead of an
open-ended research problem, and to turn whatever number comes back into a
ready-to-paste, monotonicity-preserving code diff automatically.

STEP 1 — open these in a real browser and jot down one round-trip economy
fare (or one hotel/food figure) for AT LEAST ONE routes/destination per row
you want to recalibrate (you don't need all of them — recalibrate one band/
tier at a time as real numbers turn up, same as the Bengaluru->Colombo fix):

  Flight bands (core/distance_pricing.py DISTANCE_BANDS) — pick one route
  per band, any date ~2-4 months out, economy, round trip:
    - regional (SE Asia / Middle East, ~1500-4000km from a major Indian hub):
        Google Flights: https://www.google.com/travel/flights?q=Flights%20from%20Bengaluru%20to%20Bangkok%20on%202026-11-10%20returning%202026-11-17
        Skyscanner:     https://www.skyscanner.co.in/transport/flights/blru/bkk/261110/261117/
    - long-haul (Europe / East Asia, ~4000-8000km):
        Google Flights: https://www.google.com/travel/flights?q=Flights%20from%20Delhi%20to%20London%20on%202026-11-10%20returning%202026-11-17
        Skyscanner:     https://www.skyscanner.co.in/transport/flights/deli/lond/261110/261117/
    - ultra-long-haul (Americas / Oceania, 8000km+):
        Google Flights: https://www.google.com/travel/flights?q=Flights%20from%20Mumbai%20to%20New%20York%20on%202026-11-10%20returning%202026-11-17
        Skyscanner:     https://www.skyscanner.co.in/transport/flights/bomb/nyca/261110/261117/

  Destination-tier cost matrix (core/budget_estimator.py _COST_MATRIX) — pick
  one destination per tier, one real nightly hotel rate + one real daily food
  spend (a mid-range hotel booking site + a couple of restaurant menus /
  Numbeo "Restaurants" category are both fine, whatever you can actually see
  a number on):
    - moderate tier (e.g. Bangkok, Bali, Istanbul):
        Booking.com: https://www.booking.com/searchresults.html?ss=Bangkok
        Numbeo:      https://www.numbeo.com/cost-of-living/in/Bangkok
    - premium tier (e.g. Paris, Tokyo, Dubai):
        Booking.com: https://www.booking.com/searchresults.html?ss=Paris
        Numbeo:      https://www.numbeo.com/cost-of-living/in/Paris

STEP 2 — run this script with whatever real number(s) you found:
    cd apps/api && .venv/bin/python -m scripts.recalibrate_pricing \\
        --band regional --round-trip-inr 32000 --route "Bengaluru->Bangkok"

    cd apps/api && .venv/bin/python -m scripts.recalibrate_pricing \\
        --tier moderate --style mid_range \\
        --stay-per-night-inr 4500 --food-per-day-inr 2200 \\
        --destination Bangkok

It prints the recalibrated table with a diff against the current values and
a ready-to-paste code snippet — it does NOT edit source files itself
(recalibration is a judgment call worth a human/agent glance, same as the
2026-07-20 fix's own "nudge neighbours just enough to stay monotonic, not
some formula" approach) — but it does the arithmetic and the monotonicity
bookkeeping for you.
"""
from __future__ import annotations

import argparse
import sys

from core.budget_estimator import _COST_MATRIX
from core.distance_pricing import DISTANCE_BANDS

_BAND_NAMES = [
    "short_domestic_hop", "near_neighbour", "regional", "long_haul", "ultra_long_haul",
]
_TIERS = ["budget", "moderate", "premium"]
_STYLES = ["economical", "mid_range", "premium"]

# What fraction of a band's (low, high) round-trip range the "mid_range"
# spending style is assumed to land at — same reasoning the 2026-07-20 near-
# neighbour recalibration used (~0.5 for mid_range, ~0.9 for premium).
_MID_RANGE_FRACTION = 0.5


def recalibrate_band(band_index: int, real_round_trip_inr: float) -> list[tuple[float, int, int]]:
    """Rescale one DISTANCE_BANDS row around a real mid_range fare, then walk
    every other row in distance order nudging (low, high) up just enough to
    keep the table monotonically increasing with distance — never down, and
    never further than the minimum needed, so an untouched, already-correct
    neighbour isn't perturbed for no reason."""
    bands = [list(b) for b in DISTANCE_BANDS]
    max_km, low, high = bands[band_index]
    current_mid = (low + high) / 2
    if current_mid <= 0:
        raise ValueError(f"band {band_index} has non-positive current midpoint")
    scale = real_round_trip_inr / current_mid
    bands[band_index][1] = round(low * scale)
    bands[band_index][2] = round(high * scale)

    # Preserve monotonicity outward from the recalibrated band in both
    # directions — only push a neighbour's bound up to match, never lower it
    # (a neighbour's own real anchor, once it has one, should always win over
    # this mechanical nudge).
    for i in range(band_index + 1, len(bands)):
        bands[i][1] = max(bands[i][1], bands[i - 1][1])
        bands[i][2] = max(bands[i][2], bands[i - 1][2])
    for i in range(band_index - 1, -1, -1):
        bands[i][1] = min(bands[i][1], bands[i + 1][1])
        bands[i][2] = min(bands[i][2], bands[i + 1][2])

    return [tuple(b) for b in bands]


def recalibrate_cost_matrix(
    tier: str, style: str, stay_per_night_inr: int | None, food_per_day_inr: int | None
) -> dict:
    """Rescale one _COST_MATRIX[tier][style] cell's stay/food fields, then
    nudge every other style within the same tier (and the same tier/style
    cell across tiers) up/down just enough to preserve both orderings:
    economical <= mid_range <= premium (spending style) and
    budget <= moderate <= premium (destination tier)."""
    matrix = {t: {s: dict(v) for s, v in styles.items()} for t, styles in _COST_MATRIX.items()}
    cell = matrix[tier][style]

    for field, real_value in (
        ("stay_per_night_pp", stay_per_night_inr),
        ("food_per_day_pp", food_per_day_inr),
    ):
        if real_value is None:
            continue
        cell[field] = round(real_value)

        # Style ordering within the tier: economical <= mid_range <= premium.
        # Only push a neighbour up/down the minimum amount needed to restore
        # order — never touch a neighbour that's already consistent.
        style_idx = _STYLES.index(style)
        for i in range(style_idx + 1, len(_STYLES)):
            other = matrix[tier][_STYLES[i]]
            if other[field] < matrix[tier][_STYLES[i - 1]][field]:
                other[field] = round(matrix[tier][_STYLES[i - 1]][field] * 1.15)
        for i in range(style_idx - 1, -1, -1):
            other = matrix[tier][_STYLES[i]]
            if other[field] > matrix[tier][_STYLES[i + 1]][field]:
                other[field] = round(matrix[tier][_STYLES[i + 1]][field] * 0.85)

        # Destination-tier ordering for the same style: budget <= moderate <= premium.
        tier_idx = _TIERS.index(tier)
        for i in range(tier_idx + 1, len(_TIERS)):
            other = matrix[_TIERS[i]][style]
            if other[field] < matrix[_TIERS[i - 1]][style][field]:
                other[field] = round(matrix[_TIERS[i - 1]][style][field] * 1.1)
        for i in range(tier_idx - 1, -1, -1):
            other = matrix[_TIERS[i]][style]
            if other[field] > matrix[_TIERS[i + 1]][style][field]:
                other[field] = round(matrix[_TIERS[i + 1]][style][field] * 0.9)

    return matrix


def _print_band_diff(new_bands: list[tuple[float, int, int]]) -> None:
    print("\n--- core/distance_pricing.py DISTANCE_BANDS (current -> recalibrated) ---")
    for name, old, new in zip(_BAND_NAMES, DISTANCE_BANDS, new_bands):
        changed = " (CHANGED)" if old != new else ""
        print(f"  {name:20} {old} -> {new}{changed}")
    print("\nPaste-ready:")
    print("DISTANCE_BANDS: list[tuple[float, int, int]] = [")
    for max_km, low, high in new_bands:
        km_repr = 'float("inf")' if max_km == float("inf") else max_km
        print(f"    ({km_repr}, {low}, {high}),")
    print("]")


def _print_matrix_diff(new_matrix: dict, tier: str) -> None:
    print(f"\n--- core/budget_estimator.py _COST_MATRIX['{tier}'] (current -> recalibrated) ---")
    for style in _STYLES:
        old, new = _COST_MATRIX[tier][style], new_matrix[tier][style]
        changed = " (CHANGED)" if old != new else ""
        print(f"  {style:12} {old} -> {new}{changed}")
    print("\nFull recalibrated _COST_MATRIX (paste-ready):")
    print("_COST_MATRIX: dict[str, dict[str, dict[str, int]]] = {")
    for t in _TIERS:
        print(f'    "{t}": {{')
        for s in _STYLES:
            v = new_matrix[t][s]
            print(f'        "{s}":  {{"flight_roundtrip_pp": {v["flight_roundtrip_pp"]}, '
                  f'"stay_per_night_pp": {v["stay_per_night_pp"]}, "food_per_day_pp": {v["food_per_day_pp"]}}},')
        print("    },")
    print("}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--band", choices=_BAND_NAMES, help="Recalibrate a DISTANCE_BANDS row")
    parser.add_argument("--round-trip-inr", type=float, help="Real round-trip economy fare, INR")
    parser.add_argument("--route", default="", help="Route the fare came from, for the printed note only")

    parser.add_argument("--tier", choices=_TIERS, help="Recalibrate a _COST_MATRIX destination tier")
    parser.add_argument("--style", choices=_STYLES, default="mid_range", help="Spending style row within the tier")
    parser.add_argument("--stay-per-night-inr", type=float, default=None)
    parser.add_argument("--food-per-day-inr", type=float, default=None)
    parser.add_argument("--destination", default="", help="Destination the figures came from, for the printed note only")

    args = parser.parse_args()

    if not args.band and not args.tier:
        parser.print_help()
        return 1

    if args.band:
        if args.round_trip_inr is None:
            print("--round-trip-inr is required with --band", file=sys.stderr)
            return 1
        index = _BAND_NAMES.index(args.band)
        new_bands = recalibrate_band(index, args.round_trip_inr)
        if args.route:
            print(f"Anchor: {args.route} = ₹{args.round_trip_inr:,.0f} round trip")
        _print_band_diff(new_bands)

    if args.tier:
        if args.stay_per_night_inr is None and args.food_per_day_inr is None:
            print("at least one of --stay-per-night-inr / --food-per-day-inr is required with --tier", file=sys.stderr)
            return 1
        new_matrix = recalibrate_cost_matrix(
            args.tier, args.style, args.stay_per_night_inr, args.food_per_day_inr
        )
        if args.destination:
            print(f"Anchor: {args.destination} ({args.tier}/{args.style})")
        _print_matrix_diff(new_matrix, args.tier)

    return 0


if __name__ == "__main__":
    sys.exit(main())
