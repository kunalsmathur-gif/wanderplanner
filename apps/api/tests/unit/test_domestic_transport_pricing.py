"""Tests for core/domestic_transport_pricing.py — India-domestic rail/bus/cab
fare estimates used as a cheaper-alternative call-out to flight pricing.

See core/distance_pricing.py's tests (if any) for the flight-band side of
this comparison; this file only covers the new module.
"""
import pytest

from core.domestic_transport_pricing import (
    BUS_RATE_PER_KM_INR,
    CAB_MAX_KM,
    RAIL_RATE_PER_KM_INR,
    estimate_domestic_alternative,
)


class TestEstimateDomesticAlternative:
    def test_rejects_unknown_class_tier(self):
        with pytest.raises(ValueError, match="class_tier"):
            estimate_domestic_alternative(500, "luxury")

    def test_rejects_non_positive_distance(self):
        with pytest.raises(ValueError, match="distance_km"):
            estimate_domestic_alternative(0, "mid_range")
        with pytest.raises(ValueError, match="distance_km"):
            estimate_domestic_alternative(-100, "mid_range")

    def test_short_hop_offers_all_three_options(self):
        # e.g. Delhi->Agra centre-to-centre (~120km) — well within both bus
        # and cab range.
        result = estimate_domestic_alternative(120, "mid_range")
        assert result["rail_inr"] is not None
        assert result["bus_inr"] is not None
        assert result["cab_inr"] is not None

    def test_long_hop_excludes_bus_and_cab(self):
        # e.g. Delhi->Chennai (~2180km) — bus and cab are not realistic;
        # only rail remains.
        result = estimate_domestic_alternative(2180, "mid_range")
        assert result["rail_inr"] is not None
        assert result["bus_inr"] is None
        assert result["cab_inr"] is None

    def test_cab_disappears_exactly_past_its_max_km(self):
        just_under = estimate_domestic_alternative(CAB_MAX_KM, "economical")
        just_over = estimate_domestic_alternative(CAB_MAX_KM + 1, "economical")
        assert just_under["cab_inr"] is not None
        assert just_over["cab_inr"] is None

    def test_rail_fare_respects_the_minimum_floor_for_a_very_short_hop(self):
        result = estimate_domestic_alternative(5, "economical")
        assert result["rail_inr"] == 150  # the documented minimum, not ~₹3

    def test_rail_fare_increases_monotonically_with_distance(self):
        near = estimate_domestic_alternative(300, "mid_range")["rail_inr"]
        far = estimate_domestic_alternative(2000, "mid_range")["rail_inr"]
        assert far > near

    def test_rail_fare_tapers_below_flat_rate_extrapolation_past_500km(self):
        # A naive flat-rate extrapolation of the 500km fare to 2000km would
        # be 4x that fare; the telescopic taper must land below that, since
        # real Indian Railways per-km fares get cheaper on longer journeys.
        fare_500 = estimate_domestic_alternative(500, "mid_range")["rail_inr"]
        fare_2000 = estimate_domestic_alternative(2000, "mid_range")["rail_inr"]
        naive_flat_rate_extrapolation = fare_500 * 4
        assert fare_2000 < naive_flat_rate_extrapolation

    def test_rail_class_tiers_are_ordered_economical_to_premium(self):
        eco = estimate_domestic_alternative(1000, "economical")["rail_inr"]
        mid = estimate_domestic_alternative(1000, "mid_range")["rail_inr"]
        prem = estimate_domestic_alternative(1000, "premium")["rail_inr"]
        assert eco < mid < prem

    def test_bus_class_tiers_are_ordered_economical_to_premium(self):
        eco = estimate_domestic_alternative(300, "economical")["bus_inr"]
        mid = estimate_domestic_alternative(300, "mid_range")["bus_inr"]
        prem = estimate_domestic_alternative(300, "premium")["bus_inr"]
        assert eco < mid < prem

    def test_bus_fare_respects_the_minimum_floor_for_a_very_short_hop(self):
        result = estimate_domestic_alternative(5, "economical")
        assert result["bus_inr"] == 200

    def test_cab_fare_respects_the_minimum_floor_for_a_very_short_hop(self):
        result = estimate_domestic_alternative(5, "economical")
        assert result["cab_inr"] == 800

    def test_all_class_tiers_covered_in_both_rate_tables(self):
        assert set(RAIL_RATE_PER_KM_INR) == {"economical", "mid_range", "premium"}
        assert set(BUS_RATE_PER_KM_INR) == {"economical", "mid_range", "premium"}
