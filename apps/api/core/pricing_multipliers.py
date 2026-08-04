"""Shared pricing multipliers: dataset-age inflation + dataset-internal peak
seasonality.

Two consumers plan to use this module (see the companion Workstream A/B
issues in the GitHub tracker): the new India-domestic rail/bus/cab bands
(`core/domestic_transport_pricing.py`) and the forthcoming Kaggle
flight-pricing calibration proposal script
(`scripts/ingest_kaggle_pricing.py`). Both need to scale a hand-anchored or
dataset-derived ₹ figure up for (a) how stale the underlying data is, and
(b) whether the specific month being priced is a peak-fare month *within
that dataset's own observed seasonality* — which is a different concept
from `core/budget_estimator.py`'s existing `_PEAK_SEASON_MULTIPLIER` (a
generic Indian-traveller-calendar heuristic applied to flight + stay
broadly, not derived from any one dataset).

IMPORTANT — these two multipliers must NOT be merged with
`budget_estimator._PEAK_SEASON_MULTIPLIER` (currently 1.25x, applied to
flight + stay). They stack multiplicatively with it and with each other,
via `combined_multiplier()`, which also guards against double-counting: if
a dataset is already documented as internally peak-adjusted (its price
already reflects seasonal variance, e.g. because it was built from a
full year of fares and the caller is quoting an annual-average figure),
pass `already_peak_adjusted=True` and `dataset_peak_multiplier` becomes a
no-op (1.0) for that call — the caller is asserting the dataset's own
number already prices in seasonality, so applying this module's factor on
top would double-count it.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Inflation multiplier — scales a dataset-derived figure up for staleness.
# ---------------------------------------------------------------------------

# Annual compounding rate applied per full year elapsed since the dataset was
# collected. 1.06 (~6%/year) is a mid-point pick between general India CPI
# (~5-6%/year, RBI's long-run target band) and India-specific travel/airfare
# inflation, which has historically run somewhat hotter than headline CPI
# (fuel surcharges, ATF price volatility) — 6% is a defensible single number
# for both, rather than maintaining two separate rates for a estimate this
# approximate. Revisit if a real CPI/travel-inflation reference is sourced
# at implementation time and disagrees meaningfully with this pick.
_ANNUAL_INFLATION_RATE = 0.06


def inflation_multiplier(dataset_year: int, reference_year: int) -> float:
    """Compounding multiplier to scale a `dataset_year`-priced figure up to
    `reference_year` price levels. Returns 1.0 if the dataset is from the
    reference year or later (never discounts a "future-dated" dataset —
    that would imply deflation, which isn't the intent here)."""
    years_elapsed = reference_year - dataset_year
    if years_elapsed <= 0:
        return 1.0
    return round((1.0 + _ANNUAL_INFLATION_RATE) ** years_elapsed, 4)


# ---------------------------------------------------------------------------
# Dataset-peak multiplier — scales for within-dataset seasonal fare variance.
# ---------------------------------------------------------------------------

# Per-dataset, per-month multiplier tables. Each dataset's own date-of-journey
# (or equivalent) column is the source for these — NOT the generic Indian-
# traveller calendar in core/budget_estimator.py. Keyed by a short dataset
# identifier the caller controls (e.g. the Kaggle dataset slug), so multiple
# datasets with different seasonality shapes can coexist here without
# colliding.
#
# "kaggle_flight_price_prediction": shubhambathwal/flight-price-prediction
# (300K rows, EaseMyTrip, 6 India metros). KNOWN GAP: this dataset only
# covers Feb-Mar 2022 — two months, both shoulder-season by the generic
# Indian-traveller calendar (see budget_estimator._GENERIC_PEAK_MONTHS: peak
# is {4,5,6,10,12,1}, and Feb/Mar are absent from that set). There is no
# within-dataset evidence for how fares behave in the other 10 months, so
# this table is intentionally left EMPTY for that dataset rather than
# guessing — `dataset_peak_multiplier()` returns 1.0 (no adjustment) for any
# month not present in a dataset's table. Callers needing peak/off-peak
# awareness for this dataset specifically should fall back to a festival/
# holiday-calendar heuristic (e.g. budget_estimator.is_peak_season) layered
# on separately, not invent a peak factor from two non-peak months of data.
_DATASET_PEAK_MULTIPLIERS: dict[str, dict[int, float]] = {
    "kaggle_flight_price_prediction": {},
}


def dataset_peak_multiplier(dataset: str, month: int, *, already_peak_adjusted: bool = False) -> float:
    """Multiplier for `month` (1-12) derived from `dataset`'s own observed
    seasonal fare variance. Returns 1.0 (no adjustment) when:
    - `already_peak_adjusted=True` — the caller's dataset-derived figure
      already prices in seasonality (see module docstring); or
    - the dataset isn't registered in `_DATASET_PEAK_MULTIPLIERS`; or
    - the dataset has no observed data for this specific month (see the
      Feb-Mar-2022-only Kaggle dataset caveat in this module's docstring).
    """
    if already_peak_adjusted:
        return 1.0
    return _DATASET_PEAK_MULTIPLIERS.get(dataset, {}).get(month, 1.0)


def combined_multiplier(
    dataset_year: int,
    reference_year: int,
    dataset: str,
    month: int,
    *,
    already_peak_adjusted: bool = False,
) -> float:
    """Multiplicative stack of `inflation_multiplier` and
    `dataset_peak_multiplier`. This is the intended single entry point for
    callers — see module docstring for why the two factors must not be
    merged into one, and why `already_peak_adjusted` exists to prevent
    double-counting seasonality a dataset has already priced in."""
    inflation = inflation_multiplier(dataset_year, reference_year)
    peak = dataset_peak_multiplier(dataset, month, already_peak_adjusted=already_peak_adjusted)
    return round(inflation * peak, 4)
