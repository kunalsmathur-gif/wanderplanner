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


class TestFoodGroundingFloor:
    """The food line item's floor is *provenance-conditional*
    (`_grounded_food_per_day`).

    A figure reconciled from per-meal prices depends on the uncalibrated
    `_FOOD_MEALS_PER_DAY` assumption, so it stays floored at the flat
    _COST_MATRIX value — grounding can only raise food, never undercut it
    (NEXT_SESSION_TODO 'item A'). A figure read directly from amounts already
    expressed per-day involves no multiplier at all, so it is trusted in both
    directions — that is the 'anchored against real daily-spend data'
    condition the floor was always meant to be temporary pending. Stay has
    neither reconciliation nor floor."""

    @pytest.mark.asyncio
    async def test_reconciled_food_below_flat_is_floored_and_not_flagged_community(self):
        from core.budget_estimator import _grounded_food_per_day

        with patch(
            "core.budget_estimator.community_food_per_day_inr",
            new=AsyncMock(return_value=(400.0, False)),
        ):
            val, based = await _grounded_food_per_day("Venice", "Italy", 6546)
        assert (val, based) == (6546, False)  # per-dish 400 discarded, flat used, reported honestly

    @pytest.mark.asyncio
    async def test_reconciled_food_above_flat_is_used(self):
        """A genuinely food-expensive destination whose reconciled per-day
        figure exceeds the flat default grounds food upward and flags it
        community-based — the point of the item-A proper fix."""
        from core.budget_estimator import _grounded_food_per_day

        with patch(
            "core.budget_estimator.community_food_per_day_inr",
            new=AsyncMock(return_value=(8000.0, False)),
        ):
            val, based = await _grounded_food_per_day("Venice", "Italy", 6546)
        assert (val, based) == (8000.0, True)

    @pytest.mark.asyncio
    async def test_directly_observed_food_below_flat_is_kept(self):
        """The floor does NOT apply to a directly-observed daily figure: no
        meals/day assumption was involved, so a genuinely cheap destination's
        real reported daily spend is allowed to come in under the flat value."""
        from core.budget_estimator import _grounded_food_per_day

        with patch(
            "core.budget_estimator.community_food_per_day_inr",
            new=AsyncMock(return_value=(900.0, True)),
        ):
            val, based = await _grounded_food_per_day("Hanoi", "Vietnam", 1800)
        assert (val, based) == (900.0, True)

    @pytest.mark.asyncio
    async def test_no_grounding_falls_back_to_flat(self):
        from core.budget_estimator import _grounded_food_per_day

        with patch(
            "core.budget_estimator.community_food_per_day_inr",
            new=AsyncMock(return_value=(None, False)),
        ):
            val, based = await _grounded_food_per_day("Nowhere", None, 1800)
        assert (val, based) == (1800, False)

    @pytest.mark.asyncio
    async def test_stay_grounding_below_flat_is_kept_no_floor(self):
        from core.budget_estimator import _STAY_PP_BOUNDS, _grounded_or_flat

        with patch("core.budget_estimator.community_median_price_inr", new=AsyncMock(return_value=500.0)):
            val, based = await _grounded_or_flat(
                "Goa", "India", "hotel accommodation nightly rate per person", 2000, _STAY_PP_BOUNDS
            )
        assert (val, based) == (500.0, True)  # a genuinely-cheap stay is allowed below flat

    @pytest.mark.asyncio
    async def test_estimator_floors_reconciled_food_but_keeps_below_flat_stay(self):
        """End-to-end: a low value hits both line items; food (reconciled, so
        floored) ignores it, stay (no floor) uses it."""

        # Signature must track community_median_price_inr's: _grounded_or_flat
        # wraps the call in `except Exception`, so a stale stub signature shows
        # up as a silent fall-back to flat rather than as a TypeError.
        async def _low_stay(dest, query_suffix, low, high, min_samples=2, context_keywords=None):
            return 400.0

        with patch("core.budget_estimator.community_median_price_inr", new=_low_stay), patch(
            "core.budget_estimator.community_food_per_day_inr",
            new=AsyncMock(return_value=(1200.0, False)),
        ):
            est = await estimate_bare_minimum_budget(_config())  # Colombo, budget tier
        assert est["food_community_based"] is False  # reconciled + below flat -> floored
        assert est["stay_community_based"] is True    # below-flat stay grounding kept

    @pytest.mark.asyncio
    async def test_estimator_keeps_directly_observed_food_below_flat(self):
        """Same end-to-end path, but with a directly-observed daily figure —
        it survives below the flat default and is honestly flagged as
        community-based."""

        async def _none(dest, query_suffix, low, high, context_keywords=None):
            return None

        with patch("core.budget_estimator.community_median_price_inr", new=_none), patch(
            "core.budget_estimator.community_food_per_day_inr",
            new=AsyncMock(return_value=(1200.0, True)),
        ):
            est = await estimate_bare_minimum_budget(_config())
        assert est["food_community_based"] is True

