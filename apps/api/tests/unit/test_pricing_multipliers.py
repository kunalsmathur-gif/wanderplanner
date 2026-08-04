"""Tests for core/pricing_multipliers.py — dataset-age inflation + dataset-
internal peak-seasonality multipliers, used by the domestic-transport-pricing
and Kaggle-flight-ingestion workstreams.

These stack multiplicatively on top of (and are independent from)
core/budget_estimator.py's existing generic `_PEAK_SEASON_MULTIPLIER` —
this file only covers the two functions in pricing_multipliers.py, not that
existing multiplier.
"""
import pytest

from core.pricing_multipliers import (
    combined_multiplier,
    dataset_peak_multiplier,
    inflation_multiplier,
)


class TestInflationMultiplier:
    def test_same_year_is_a_no_op(self):
        assert inflation_multiplier(2026, 2026) == 1.0

    def test_future_dated_dataset_is_a_no_op_not_a_discount(self):
        # A dataset "from" a later year than the reference year shouldn't
        # imply deflation — treat it as no adjustment, not < 1.0.
        assert inflation_multiplier(2027, 2026) == 1.0

    def test_one_year_elapsed_compounds_by_the_annual_rate(self):
        assert inflation_multiplier(2025, 2026) == pytest.approx(1.06, abs=1e-4)

    def test_multiple_years_compound_not_flat_multiply(self):
        # 3 years at 6%/year compounding: 1.06^3 = 1.191016, NOT 1.18 (flat
        # 3 x 6%) — compounding is the whole point of the function existing
        # instead of a simple `1 + rate * years` formula.
        three_year = inflation_multiplier(2022, 2025)
        assert three_year == pytest.approx(1.06 ** 3, abs=1e-4)
        assert three_year != pytest.approx(1.18, abs=1e-3)

    def test_monotonically_increases_with_staleness(self):
        one_year = inflation_multiplier(2025, 2026)
        two_years = inflation_multiplier(2024, 2026)
        three_years = inflation_multiplier(2023, 2026)
        assert one_year < two_years < three_years


class TestDatasetPeakMultiplier:
    def test_unregistered_dataset_is_a_no_op(self):
        assert dataset_peak_multiplier("some_unknown_dataset", 6) == 1.0

    def test_kaggle_flight_dataset_has_no_peak_data_for_any_month(self):
        # The Kaggle flight-price-prediction dataset only covers Feb-Mar
        # 2022 — no within-dataset evidence for any month's peak behaviour,
        # so every month should currently return the 1.0 no-op, not a guess.
        for month in range(1, 13):
            assert dataset_peak_multiplier("kaggle_flight_price_prediction", month) == 1.0

    def test_already_peak_adjusted_forces_a_no_op_even_for_a_registered_dataset(self):
        # Even if a future dataset gets real per-month entries, the
        # already_peak_adjusted escape hatch must always win, to prevent
        # double-counting seasonality a caller's figure already prices in.
        assert dataset_peak_multiplier(
            "kaggle_flight_price_prediction", 6, already_peak_adjusted=True
        ) == 1.0


class TestCombinedMultiplier:
    def test_stacks_inflation_and_peak_multiplicatively(self):
        # With the Kaggle dataset's peak table currently empty, this should
        # reduce to exactly the inflation multiplier alone.
        combined = combined_multiplier(2022, 2026, "kaggle_flight_price_prediction", 6)
        assert combined == inflation_multiplier(2022, 2026)

    def test_already_peak_adjusted_flows_through_to_the_peak_factor_only(self):
        # Inflation must still apply even when peak-adjustment is skipped —
        # already_peak_adjusted only suppresses double-counting seasonality,
        # not staleness.
        combined = combined_multiplier(
            2022, 2026, "kaggle_flight_price_prediction", 6, already_peak_adjusted=True
        )
        assert combined == inflation_multiplier(2022, 2026)

    def test_same_year_no_registered_peak_data_is_a_full_no_op(self):
        assert combined_multiplier(2026, 2026, "unknown_dataset", 6) == 1.0
