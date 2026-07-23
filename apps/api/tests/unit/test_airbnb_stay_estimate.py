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
    """The food line item reconciles per-meal community prices to a per-day
    figure (per_day_meal_multiplier=_FOOD_MEALS_PER_DAY) and then floors it at
    the flat _COST_MATRIX value (floor=True): Wikivoyage 'Eat' prices are
    per-dish/per-meal, so grounding can only ever *raise* food above the
    researched flat bare-minimum, never undercut it. Stay has no such floor
    and no reconciliation (NEXT_SESSION_TODO 'item A')."""

    @pytest.mark.asyncio
    async def test_food_grounding_below_flat_is_floored_and_not_flagged_community(self):
        from core.budget_estimator import _FOOD_PP_BOUNDS, _grounded_or_flat

        with patch("core.budget_estimator.community_median_price_inr", new=AsyncMock(return_value=400.0)):
            val, based = await _grounded_or_flat(
                "Venice", "Italy", "food meal daily cost per person", 6546, _FOOD_PP_BOUNDS, floor=True
            )
        assert (val, based) == (6546, False)  # per-dish 400 discarded, flat used, reported honestly

    @pytest.mark.asyncio
    async def test_food_grounding_above_flat_is_used(self):
        from core.budget_estimator import _FOOD_PP_BOUNDS, _grounded_or_flat

        with patch("core.budget_estimator.community_median_price_inr", new=AsyncMock(return_value=8000.0)):
            val, based = await _grounded_or_flat(
                "Venice", "Italy", "food meal daily cost per person", 6546, _FOOD_PP_BOUNDS, floor=True
            )
        assert (val, based) == (8000.0, True)  # legitimately-higher grounding still wins

    @pytest.mark.asyncio
    async def test_stay_grounding_below_flat_is_kept_no_floor(self):
        from core.budget_estimator import _STAY_PP_BOUNDS, _grounded_or_flat

        with patch("core.budget_estimator.community_median_price_inr", new=AsyncMock(return_value=500.0)):
            val, based = await _grounded_or_flat(
                "Goa", "India", "hotel accommodation nightly rate per person", 2000, _STAY_PP_BOUNDS, floor=False
            )
        assert (val, based) == (500.0, True)  # a genuinely-cheap stay is allowed below flat

    @pytest.mark.asyncio
    async def test_estimator_floors_food_but_keeps_below_flat_stay(self):
        """End-to-end: one low grounded value hits both line items; food (floored)
        ignores it, stay (no floor) uses it — proving the floor is food-only."""

        async def _low(dest, query_suffix, low, high, context_keywords=None, per_day_meal_multiplier=None):
            # A single per-meal figure; even reconciled to per-day it stays
            # below both the flat food (1800) and flat stay (2000) budget-tier
            # values, so it exercises the floor (food) vs no-floor (stay) split.
            return 400.0 * (per_day_meal_multiplier or 1)

        with patch("core.budget_estimator.community_median_price_inr", new=_low):
            est = await estimate_bare_minimum_budget(_config())  # Colombo, budget tier
        assert est["food_community_based"] is False  # floored to flat
        assert est["stay_community_based"] is True    # below-flat stay grounding kept

    @pytest.mark.asyncio
    async def test_food_call_passes_per_day_multiplier_but_stay_does_not(self):
        """The food line item must reconcile per-meal->per-day (multiplier set);
        the stay line item must not (its amounts are already per-night)."""
        from core.budget_estimator import _FOOD_MEALS_PER_DAY, estimate_bare_minimum_budget

        seen: dict[str, float | None] = {}

        async def _capture(dest, query_suffix, low, high, min_samples=2, limit=5,
                           context_keywords=None, per_day_meal_multiplier=None):
            key = "food" if "food" in query_suffix else "stay"
            seen[key] = per_day_meal_multiplier
            return None  # force flat fallback; we only care about the kwargs

        with patch("core.budget_estimator.community_median_price_inr", new=_capture):
            await estimate_bare_minimum_budget(_config())

        assert seen["food"] == _FOOD_MEALS_PER_DAY
        assert seen["stay"] is None

    @pytest.mark.asyncio
    async def test_reconciled_food_above_flat_flips_community_true(self):
        """A genuinely food-expensive destination whose reconciled per-day
        figure exceeds the flat default correctly grounds food upward and
        flags it community-based — the whole point of the item-A proper fix."""
        from core.budget_estimator import _FOOD_PP_BOUNDS, _FOOD_MEALS_PER_DAY, _grounded_or_flat

        # community_median_price_inr already returns the reconciled per-day
        # median here (the multiplier is applied inside it); 8000 > flat 6546.
        with patch("core.budget_estimator.community_median_price_inr", new=AsyncMock(return_value=8000.0)):
            val, based = await _grounded_or_flat(
                "Venice", "Italy", "food meal daily cost per person", 6546, _FOOD_PP_BOUNDS,
                floor=True, per_day_meal_multiplier=_FOOD_MEALS_PER_DAY,
            )
        assert (val, based) == (8000.0, True)

