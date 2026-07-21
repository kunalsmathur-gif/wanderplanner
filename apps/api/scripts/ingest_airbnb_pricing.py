"""Helper for extending core/airbnb_pricing.py's seed list with a new city.

Unlike scripts/recalibrate_pricing.py (which needs a human to eyeball a
JS-rendered site), Inside Airbnb's data is directly downloadable, so this
script does the whole computation end-to-end: given a city's Inside Airbnb
"visualisations/listings.csv" URL (find it at https://insideairbnb.com/get-the-data/
— only ~100 cities worldwide are covered, mostly Europe/Americas/some Asia-
Pacific), it downloads the CSV, computes the median "Entire home/apt" nightly
price, converts to INR, and prints a ready-to-paste `AIRBNB_HOTEL_EQUIVALENT_PP_INR`
entry (median ÷ 2 for double occupancy ÷ `_AIRBNB_STAY_DISCOUNT_MULTIPLIER`
to approximate a hotel-equivalent rate — see that constant's docstring in
core/budget_estimator.py for how 0.30 was derived and why the conversion
direction is "divide", not "multiply").

Only use this for a city where Wikivoyage has NO usable inline hotel-pricing
data (check the article's Sleep section / district sub-articles first) —
if Wikivoyage already has real listing prices, prefer feeding those into
`scripts/recalibrate_pricing.py` instead, since that's a like-for-like hotel
comparison rather than an Airbnb-derived proxy.

Usage:
    cd apps/api && .venv/bin/python -m scripts.ingest_airbnb_pricing \\
        --city Bali \\
        --csv-url https://data.insideairbnb.com/indonesia/bali/bali/2026-06-30/visualisations/listings.csv \\
        --currency-to-usd-rate 16300  # units of local currency per 1 USD

It does NOT edit core/airbnb_pricing.py itself — paste the printed entry in
by hand (same "human/agent glance before committing a real number" principle
as recalibrate_pricing.py).
"""
from __future__ import annotations

import argparse
import csv
import io
import urllib.request

_AIRBNB_STAY_DISCOUNT_MULTIPLIER = 0.30  # keep in sync with core/budget_estimator.py
_USD_TO_INR_RATE = 87.0  # keep in sync with core/config.py's usd_to_inr_rate


def _median(values: list[float]) -> float:
    values = sorted(values)
    n = len(values)
    if n == 0:
        raise ValueError("no entire-home/apt listings with a usable price found")
    mid = n // 2
    return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--city", required=True, help="City name as it should appear in the seed dict key")
    parser.add_argument("--csv-url", required=True, help="Inside Airbnb visualisations/listings.csv URL for the city")
    parser.add_argument(
        "--currency-to-usd-rate", type=float, required=True,
        help="Units of the listing's local currency per 1 USD (check a live FX rate)",
    )
    args = parser.parse_args()

    with urllib.request.urlopen(args.csv_url) as response:
        raw = response.read().decode("utf-8", errors="replace")

    prices = []
    for row in csv.DictReader(io.StringIO(raw)):
        if row.get("room_type") != "Entire home/apt":
            continue
        try:
            price = float(row["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if price > 0:
            prices.append(price)

    median_local = _median(prices)
    inr_per_local_unit = _USD_TO_INR_RATE / args.currency_to_usd_rate
    median_pp_inr = (median_local * inr_per_local_unit) / 2  # double occupancy
    hotel_equivalent_pp_inr = round(median_pp_inr / _AIRBNB_STAY_DISCOUNT_MULTIPLIER)

    key = args.city.strip().lower()
    print(f"n entire-home/apt listings: {len(prices)}")
    print(f"median local-currency price/night: {median_local:,.0f}")
    print(f"median INR/pp/night (raw Airbnb): {median_pp_inr:,.0f}")
    print(f"hotel-equivalent INR/pp/night (÷{_AIRBNB_STAY_DISCOUNT_MULTIPLIER}): {hotel_equivalent_pp_inr:,}")
    print()
    print("Paste into core/airbnb_pricing.py's AIRBNB_HOTEL_EQUIVALENT_PP_INR dict:")
    print(f'    "{key}": {hotel_equivalent_pp_inr},')


if __name__ == "__main__":
    main()
