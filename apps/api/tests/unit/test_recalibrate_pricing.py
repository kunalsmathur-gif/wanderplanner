"""Unit tests for `scripts/recalibrate_pricing.py` — the budget-estimator
recalibration helper (docs/NEXT_SESSION_TODO.md item 10). Only the pure
arithmetic/monotonicity logic is under test; the module's CLI/browser-link
guidance is print-only and not exercised here.
"""
from __future__ import annotations

from core.budget_estimator import _COST_MATRIX
from core.distance_pricing import DISTANCE_BANDS
from scripts.recalibrate_pricing import recalibrate_band, recalibrate_cost_matrix


class TestRecalibrateBand:
    def test_rescales_target_band_around_real_anchor(self):
        # regional band index = 2
        new_bands = recalibrate_band(2, 32000)
        _, low, high = new_bands[2]
        assert (low + high) / 2 == 32000

    def test_leaves_untouched_bands_unchanged_when_already_monotonic(self):
        new_bands = recalibrate_band(2, 32000)
        assert new_bands[0] == DISTANCE_BANDS[0]
        assert new_bands[1] == DISTANCE_BANDS[1]

    def test_pushes_later_bands_up_to_preserve_monotonicity(self):
        # An anchor far above the current long_haul band's range must not
        # leave ultra_long_haul (the next band) undercutting it.
        new_bands = recalibrate_band(3, 90000)  # long_haul index = 3
        long_haul = new_bands[3]
        ultra = new_bands[4]
        assert ultra[1] >= long_haul[1]
        assert ultra[2] >= long_haul[2]

    def test_pulls_earlier_bands_down_to_preserve_monotonicity(self):
        # An anchor far below the current regional band's range must not
        # leave near_neighbour (the previous band) exceeding it.
        new_bands = recalibrate_band(2, 8000)  # regional index = 2, well below its current range
        near_neighbour = new_bands[1]
        regional = new_bands[2]
        assert near_neighbour[1] <= regional[1]
        assert near_neighbour[2] <= regional[2]

    def test_result_is_fully_monotonic_low_and_high(self):
        for band_index in range(len(DISTANCE_BANDS)):
            new_bands = recalibrate_band(band_index, 45000)
            lows = [b[1] for b in new_bands]
            highs = [b[2] for b in new_bands]
            assert lows == sorted(lows)
            assert highs == sorted(highs)


class TestRecalibrateCostMatrix:
    def test_rescales_target_cell(self):
        new_matrix = recalibrate_cost_matrix("moderate", "mid_range", 4500, 2200)
        cell = new_matrix["moderate"]["mid_range"]
        assert cell["stay_per_night_pp"] == 4500
        assert cell["food_per_day_pp"] == 2200

    def test_leaves_other_fields_unspecified_untouched(self):
        new_matrix = recalibrate_cost_matrix("moderate", "mid_range", 4500, None)
        cell = new_matrix["moderate"]["mid_range"]
        assert cell["food_per_day_pp"] == _COST_MATRIX["moderate"]["mid_range"]["food_per_day_pp"]

    def test_style_ordering_preserved_within_tier(self):
        # A mid_range anchor above the current premium stay figure must push
        # premium up too (economical <= mid_range <= premium must hold).
        new_matrix = recalibrate_cost_matrix("moderate", "mid_range", 10000, None)
        moderate = new_matrix["moderate"]
        assert moderate["economical"]["stay_per_night_pp"] <= moderate["mid_range"]["stay_per_night_pp"]
        assert moderate["mid_range"]["stay_per_night_pp"] <= moderate["premium"]["stay_per_night_pp"]

    def test_tier_ordering_preserved_across_tiers(self):
        # A moderate/mid_range anchor above budget tier's untouched value must
        # not leave budget's mid_range exceeding moderate's.
        new_matrix = recalibrate_cost_matrix("moderate", "mid_range", 500, None)
        assert new_matrix["budget"]["mid_range"]["stay_per_night_pp"] <= new_matrix["moderate"]["mid_range"]["stay_per_night_pp"]

    def test_untouched_tiers_left_alone_when_already_consistent(self):
        new_matrix = recalibrate_cost_matrix("moderate", "mid_range", 4500, 2200)
        assert new_matrix["budget"] == _COST_MATRIX["budget"]
        assert new_matrix["premium"] == _COST_MATRIX["premium"]

    def test_does_not_mutate_the_real_cost_matrix(self):
        before = {t: {s: dict(v) for s, v in styles.items()} for t, styles in _COST_MATRIX.items()}
        recalibrate_cost_matrix("premium", "premium", 999999, 999999)
        assert _COST_MATRIX == before
