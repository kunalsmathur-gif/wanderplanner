"""Kaggle flight-fare calibration-proposal script (Workstream B).

Reads an already-downloaded Kaggle "Flight Price Prediction" CSV
(`shubhambathwal/flight-price-prediction` — CC0, EaseMyTrip, 6 India
metros, March 2022 — see `docs/kaggle-data-runbook.md` for how to get the
file) and produces a **calibration proposal**: median/percentile
round-trip fares per `core/distance_pricing.py` `DISTANCE_BANDS` bucket,
inflation-adjusted via `core/pricing_multipliers.py` for dataset staleness,
printed alongside the *current* band figures for a human to compare.

Targets the dataset's `economy.csv` file specifically (columns: `date`,
`airline`, `ch_code`, `num_code`, `dep_time`, `from`, `time_taken`, `stop`,
`arr_time`, `to`, `price`) — the same mirror also ships `business.csv`
(same shape, business-class fares — out of scope, `DISTANCE_BANDS` models
economy) and `Clean_Dataset.csv` (combined economy+business with a `class`
column but no journey date, so it can't feed the peak-multiplier lookup).
Verified live against the real download 2026-08 (see `docs/
kaggle-data-runbook.md`) — actual columns/values differ from the dataset's
older/other mirrors (no `Date_of_Journey`, no `Banglore` misspelling in
this version; city names are `from`/`to` with plain "Bangalore").

Like `scripts/recalibrate_pricing.py` and `scripts/ingest_airbnb_pricing.py`,
this is **propose-only** — it never writes to `core/distance_pricing.py`.
Review the JSON output, then hand-edit `DISTANCE_BANDS` (or feed a chosen
anchor into `scripts/recalibrate_pricing.py` for a monotonicity-safe diff).

Deliberately does NOT depend on the `kaggle` package — it only ever reads a
local CSV, so it stays usable without live Kaggle credentials (e.g. in this
repo's unit tests, against a small fixture CSV) and doesn't need the
`kaggle` package added to `requirements.txt` (see `docs/kaggle-data-runbook.md`
§3/§4 for the reasoning).

Usage:
    cd apps/api && .venv/bin/python -m scripts.ingest_kaggle_pricing \\
        --csv-path /tmp/kaggle/Data_Train.csv \\
        --reference-year 2026 \\
        --out proposal.json  # optional
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict

from core.distance_pricing import DISTANCE_BANDS, haversine_km
from core.pricing_multipliers import combined_multiplier

# Dataset slug used as the key into core/pricing_multipliers.py's
# per-dataset peak-seasonality table.
_DATASET_SLUG = "kaggle_flight_price_prediction"

# Year the dataset's fares are priced in — March 2022 (economy.csv's full
# `date` range), per live verification against the real download.
_DATASET_YEAR = 2022

# Hardcoded lat/lon for the 6 India metros this specific Kaggle dataset
# covers (`from`/`to` columns). Not a general-purpose geocoder — scoped
# tightly to this one dataset's known city set. "banglore" (missing the
# second "a") is kept as an alias since other mirrors/versions of this
# same dataset are known to use that misspelling, even though the
# `economy.csv`/`business.csv` files verified live in 2026-08 use the
# correct "Bangalore" spelling.
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "kolkata": (22.5726, 88.3639),
    "chennai": (13.0827, 80.2707),
    "bangalore": (12.9716, 77.5946),
    "banglore": (12.9716, 77.5946),  # alias: misspelling used by other mirrors of this dataset
    "hyderabad": (17.3850, 78.4867),
    "cochin": (9.9312, 76.2673),
    "kochi": (9.9312, 76.2673),
}

# Human-readable label per DISTANCE_BANDS index, for the printed proposal.
_BAND_LABELS = [
    "short_domestic_hop",
    "domestic_near_neighbour",
    "regional_international",
    "long_haul",
    "ultra_long_haul",
]


def _normalise_city(name: str) -> str | None:
    key = name.strip().lower()
    return key if key in _CITY_COORDS else None


def _band_index_for_km(km: float) -> int:
    for i, (max_km, _low, _high) in enumerate(DISTANCE_BANDS):
        if km <= max_km:
            return i
    return len(DISTANCE_BANDS) - 1


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile (0-100) over an already-sorted list."""
    if not sorted_values:
        raise ValueError("no values to compute a percentile over")
    n = len(sorted_values)
    idx = max(0, min(n - 1, round(pct / 100 * (n - 1))))
    return sorted_values[idx]


def _parse_month(date_str: str) -> int | None:
    """Best-effort month extraction from the dataset's `date` column,
    observed as `DD-MM-YYYY` in the verified live download. Returns None
    (rather than raising) for any row whose format doesn't match, so one
    malformed row doesn't abort the whole run."""
    parts = date_str.strip().split("-")
    if len(parts) != 3:
        return None
    try:
        month = int(parts[1])
    except ValueError:
        return None
    return month if 1 <= month <= 12 else None


def _parse_price(price_str: str) -> float | None:
    """Parses the dataset's `price` column, which uses a comma thousands
    separator (e.g. `"5,953"`). Returns None for anything unparseable."""
    try:
        return float(price_str.replace(",", "").strip())
    except (AttributeError, ValueError):
        return None


def load_fares_by_band(csv_path: str, reference_year: int) -> dict[int, list[float]]:
    """Reads the CSV at `csv_path` (dataset's `economy.csv` shape: `date`,
    `from`, `to`, `price`, ...) and buckets each row's inflation-adjusted
    round-trip fare INR into a `DISTANCE_BANDS` index. Rows with an unknown
    city, unparseable price, or unparseable date are skipped (not counted
    as an error — this is a proposal tool, not a strict pipeline)."""
    by_band: dict[int, list[float]] = defaultdict(list)
    with open(csv_path, newline="", encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            source = _normalise_city(row.get("from", ""))
            destination = _normalise_city(row.get("to", ""))
            if source is None or destination is None or source == destination:
                continue

            one_way_price = _parse_price(row.get("price", ""))
            if one_way_price is None or one_way_price <= 0:
                continue

            month = _parse_month(row.get("date", ""))
            if month is None:
                continue

            src_lat, src_lon = _CITY_COORDS[source]
            dst_lat, dst_lon = _CITY_COORDS[destination]
            km = haversine_km(src_lat, src_lon, dst_lat, dst_lon)
            band_index = _band_index_for_km(km)

            multiplier = combined_multiplier(
                dataset_year=_DATASET_YEAR,
                reference_year=reference_year,
                dataset=_DATASET_SLUG,
                month=month,
            )
            # Dataset prices one-way fares; approximate round trip as 2x
            # one-way (no evidence of a return-leg discount/premium in this
            # dataset, so a flat doubling is the least-assuming approximation).
            round_trip_inr = one_way_price * 2 * multiplier
            by_band[band_index].append(round_trip_inr)

    return by_band


def build_proposal(by_band: dict[int, list[float]]) -> dict:
    proposal: dict = {"bands": []}
    for index, (max_km, current_low, current_high) in enumerate(DISTANCE_BANDS):
        fares = sorted(by_band.get(index, []))
        entry = {
            "band": _BAND_LABELS[index] if index < len(_BAND_LABELS) else f"band_{index}",
            "current_low_inr": current_low,
            "current_high_inr": current_high,
            "n_fares": len(fares),
        }
        if fares:
            entry["proposed_p25_inr"] = round(_percentile(fares, 25))
            entry["proposed_median_inr"] = round(_percentile(fares, 50))
            entry["proposed_p75_inr"] = round(_percentile(fares, 75))
        proposal["bands"].append(entry)
    return proposal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv-path", required=True, help="Path to the already-downloaded Kaggle CSV")
    parser.add_argument(
        "--reference-year", type=int, required=True,
        help="Current year to inflation-adjust the (2022-priced) dataset up to",
    )
    parser.add_argument("--out", default=None, help="Optional path to also write the JSON proposal to")
    args = parser.parse_args()

    by_band = load_fares_by_band(args.csv_path, args.reference_year)
    if not any(by_band.values()):
        print("No usable fares found — check --csv-path points at the real dataset file.", file=sys.stderr)
        return 1

    proposal = build_proposal(by_band)
    output = json.dumps(proposal, indent=2)
    print(output)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\nWrote proposal to {args.out}", file=sys.stderr)

    print(
        "\nThis is a PROPOSAL ONLY — core/distance_pricing.py DISTANCE_BANDS was "
        "NOT modified. Review the figures above, then hand-edit or feed a chosen "
        "anchor into scripts/recalibrate_pricing.py.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
