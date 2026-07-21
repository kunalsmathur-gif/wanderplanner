"""Tests for the Airbnb/vacation-rental stay-estimate path in
core/budget_estimator.py: `wants_airbnb_stay()` (keyword detection) and its
wiring into `estimate_bare_minimum_budget()`.

Kept in a separate file from test_budget_estimator.py because that file has
a pre-existing, unrelated Python-3.9 collection error (a `X | None` union
type hint) that isn't caused by or fixed here — see NEXT_SESSION_TODO.md.
"""
from unittest.mock import AsyncMock, patch

import pytest

from core.budget_estimator import (
    _AIRBNB_STAY_DISCOUNT_MULTIPLIER,
    estimate_bare_minimum_budget,
    wants_airbnb_stay,
)

COLOMBO = {"city": "Colombo", "country": "Sri Lanka", "lat": 6.9271, "lon": 79.8612}
ISTANBUL = {"city": "Istanbul", "country": "Turkey", "lat": 41.0082, "lon": 28.9784}


def _config(**overrides):
    config = {"group": {"adults": 2}, "destination": dict(COLOMBO)}
    config.update(overrides)
    return config


@pytest.fixture(autouse=True)
def no_community_grounding():
    """Deterministic: simulate today's real-world state (RAG grounding
    returns nothing) so the flat _COST_MATRIX rate is what gets discounted."""
    with patch("core.budget_estimator.community_median_price_inr", new=AsyncMock(return_value=None)):
        yield


class TestWantsAirbnbStay:
    def test_none_or_empty_text_is_false(self):
        assert wants_airbnb_stay(None) is False
        assert wants_airbnb_stay("") is False

    def test_no_keyword_is_false(self):
        assert wants_airbnb_stay("We'd like a nice 4-star hotel please") is False

    @pytest.mark.parametrize(
        "text",
        [
            "Can we book an Airbnb instead of a hotel?",
            "looking for an AIRBNB in the city centre",
            "prefer an air bnb this time",
            "we want a vacation rental, not a hotel",
            "self-catering apartment would be great",
            "a self catering place near the beach",
        ],
    )
    def test_keyword_variants_detected(self, text):
        assert wants_airbnb_stay(text) is True

    def test_substring_inside_unrelated_word_does_not_false_positive(self):
        # "airbnb" should not spuriously match on unrelated text containing
        # partial overlaps like "air" or "bnb" alone.
        assert wants_airbnb_stay("we'd like an air-conditioned room please") is False


class TestAirbnbStayEstimate:
    @pytest.mark.asyncio
    async def test_airbnb_hint_discounts_stay_and_flags_result(self):
        config = _config()
        hotel_estimate = await estimate_bare_minimum_budget(config, hint_text=None)
        airbnb_estimate = await estimate_bare_minimum_budget(config, hint_text="please find us an Airbnb")

        assert hotel_estimate["stay_airbnb_based"] is False
        assert airbnb_estimate["stay_airbnb_based"] is True
        # Airbnb stay component should be meaningfully cheaper than the
        # hotel-based one (discounted by _AIRBNB_STAY_DISCOUNT_MULTIPLIER),
        # and food/flights should be unaffected.
        assert airbnb_estimate["breakdown"]["stay_inr"] < hotel_estimate["breakdown"]["stay_inr"]
        assert airbnb_estimate["breakdown"]["food_inr"] == hotel_estimate["breakdown"]["food_inr"]
        assert airbnb_estimate["breakdown"]["flights_inr"] == hotel_estimate["breakdown"]["flights_inr"]

        expected_ratio = _AIRBNB_STAY_DISCOUNT_MULTIPLIER
        actual_ratio = airbnb_estimate["breakdown"]["stay_inr"] / hotel_estimate["breakdown"]["stay_inr"]
        assert abs(actual_ratio - expected_ratio) < 0.02

    @pytest.mark.asyncio
    async def test_no_airbnb_hint_leaves_stay_unchanged(self):
        config = _config()
        estimate = await estimate_bare_minimum_budget(config, hint_text="a mid-range hotel is fine")
        assert estimate["stay_airbnb_based"] is False


class TestAirbnbHotelEquivalentFallback:
    @pytest.mark.asyncio
    async def test_seeded_city_uses_airbnb_derived_rate_not_generic_flat(self):
        from core.budget_estimator import _COST_MATRIX, resolve_destination_tier

        config = _config(destination=dict(ISTANBUL))
        estimate = await estimate_bare_minimum_budget(config)

        tier = resolve_destination_tier(ISTANBUL["city"], ISTANBUL["country"])
        generic_flat_stay_pp = _COST_MATRIX[tier]["mid_range"]["stay_per_night_pp"]
        nights = max(1, estimate["duration_days"] - 1)

        assert estimate["stay_airbnb_fallback_used"] is True
        # 2 adults * nights * seeded per-person rate, not the generic flat rate.
        assert estimate["breakdown"]["stay_inr"] != 2 * nights * generic_flat_stay_pp

    @pytest.mark.asyncio
    async def test_unseeded_city_does_not_use_airbnb_fallback(self):
        config = _config()  # Colombo — not in the seed list
        estimate = await estimate_bare_minimum_budget(config)
        assert estimate["stay_airbnb_fallback_used"] is False

    @pytest.mark.asyncio
    async def test_explicit_airbnb_request_combines_with_seeded_fallback(self):
        """When both apply, the explicit-request discount is applied on top
        of the Airbnb-derived hotel-equivalent rate — round-tripping back
        toward the raw Airbnb price rather than double-counting."""
        config = _config(destination=dict(ISTANBUL))
        hotel_equivalent = await estimate_bare_minimum_budget(config, hint_text=None)
        airbnb_requested = await estimate_bare_minimum_budget(config, hint_text="we want an Airbnb")

        assert hotel_equivalent["stay_airbnb_fallback_used"] is True
        assert airbnb_requested["stay_airbnb_fallback_used"] is True
        assert airbnb_requested["stay_airbnb_based"] is True
        assert airbnb_requested["breakdown"]["stay_inr"] < hotel_equivalent["breakdown"]["stay_inr"]

