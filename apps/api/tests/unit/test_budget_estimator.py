"""Tests for core/budget_estimator.py — the wizard-chat budget recommendation.

Covers the bugs fixed: (1) flight cost used one flat number per destination
tier regardless of departure city, (2) Anya never asked for a departure city
before quoting a flight-inclusive budget, (3) stay/food used the same flat
per-destination-tier number regardless of the specific destination, now
overridable by real community-reported data when the RAG corpus has it
(currently empty in production — see core/budget_estimator.py's docstring —
so `community_median_price_inr` is mocked to return None by default here,
matching that real-world state).
"""
from unittest.mock import AsyncMock, patch

import pytest

from core.budget_estimator import budget_estimate_prompt_hint, estimate_bare_minimum_budget

BENGALURU = {"city": "Bengaluru", "lat": 12.9716, "lon": 77.5946}
COLOMBO = {"city": "Colombo", "country": "Sri Lanka", "lat": 6.9271, "lon": 79.8612}


def _config(**overrides):
    config = {
        "group": {"adults": 2},
        "destination": dict(COLOMBO),
    }
    config.update(overrides)
    return config


@pytest.fixture(autouse=True)
def no_community_grounding():
    """Default: simulate today's real-world state (Reddit/Wikivoyage
    collections empty) so these tests are deterministic and don't hit the
    network. Tests that want to exercise the grounded path override this
    via `community_grounding(...)`."""
    with patch("core.budget_estimator.community_median_price_inr", new=AsyncMock(return_value=None)):
        yield


def community_grounding(*, stay: float | None = None, food: float | None = None):
    """Returns a patch() context manager that makes community_median_price_inr
    answer `stay` for accommodation queries and `food` for food queries."""

    def _fake(dest_city, query_suffix, low, high, min_samples=2, limit=5):
        if "hotel" in query_suffix or "accommodation" in query_suffix:
            return stay
        if "food" in query_suffix or "meal" in query_suffix:
            return food
        return None

    return patch("core.budget_estimator.community_median_price_inr", new=AsyncMock(side_effect=_fake))


async def test_missing_group_returns_none():
    config = _config(group={})
    assert await estimate_bare_minimum_budget(config) is None


async def test_missing_origin_still_returns_a_number_with_flat_fallback():
    # estimate_bare_minimum_budget itself must NOT hard-require origin —
    # services/comparison.py calls it directly for destination comparisons
    # without ever collecting a departure city.
    config = _config()
    estimate = await estimate_bare_minimum_budget(config)
    assert estimate is not None
    assert estimate["flight_distance_based"] is False
    assert estimate["breakdown"]["flights_inr"] > 0


async def test_origin_with_coords_uses_distance_band_not_flat_number():
    config = _config(origin=dict(BENGALURU))
    estimate = await estimate_bare_minimum_budget(config)
    assert estimate["flight_distance_based"] is True
    # Bengaluru -> Colombo (~750km, near-neighbour band, recalibrated against
    # a real ₹27,000 round-trip fare found for Nov 2026 — see
    # core/distance_pricing.py). mid_range should land close to that real
    # fare, not the old flat ~₹10,000 guess.
    per_person_flight = estimate["breakdown"]["flights_inr"] / 2
    assert 12000 <= per_person_flight <= 30000


async def test_same_destination_different_origin_gives_different_flight_cost():
    near = await estimate_bare_minimum_budget(_config(origin=dict(BENGALURU)))
    far = await estimate_bare_minimum_budget(
        _config(destination={**COLOMBO}, origin={"city": "New York", "lat": 40.7128, "lon": -74.0060})
    )
    assert near["breakdown"]["flights_inr"] != far["breakdown"]["flights_inr"]


async def test_hint_asks_for_departure_city_before_quoting():
    config = _config()  # group + destination known, no origin
    hint = await budget_estimate_prompt_hint(config)
    assert "DEPARTURE CITY" in hint
    assert "₹" not in hint  # must not leak a number before asking


async def test_hint_quotes_a_number_once_origin_known():
    config = _config(origin=dict(BENGALURU))
    hint = await budget_estimate_prompt_hint(config)
    assert "DEPARTURE CITY" not in hint
    assert "₹" in hint


async def test_hint_skips_origin_gate_when_flights_prebooked():
    # If the user already told Anya their real flight cost, there's nothing
    # left to estimate — don't block on departure city in that case.
    config = _config(prebooked_flights_inr=27000)
    hint = await budget_estimate_prompt_hint(config)
    assert "DEPARTURE CITY" not in hint
    assert "₹" in hint


async def test_distance_band_scales_with_traveller_level():
    economical = await estimate_bare_minimum_budget(
        _config(origin=dict(BENGALURU)), hint_text="keep it cheap and economical"
    )
    premium = await estimate_bare_minimum_budget(
        _config(origin=dict(BENGALURU)), hint_text="we want a luxurious trip"
    )
    assert economical["breakdown"]["flights_inr"] < premium["breakdown"]["flights_inr"]


async def test_stay_and_food_fall_back_to_flat_tier_when_corpus_empty():
    # This is today's real-world default (see fixture above) — must not
    # break or silently zero out the estimate.
    estimate = await estimate_bare_minimum_budget(_config())
    assert estimate["stay_community_based"] is False
    assert estimate["food_community_based"] is False
    # Regression guard for the recalibrated food figure (see _COST_MATRIX's
    # comment) — 5 assumed days, 4 nights, 2 adults, budget-tier mid_range:
    # stay = 2000*4*2 = 16000, food = 1800*5*2 = 18000.
    assert estimate["breakdown"]["stay_inr"] == 16000
    assert estimate["breakdown"]["food_inr"] == 18000


async def test_stay_and_food_use_real_community_data_when_available():
    with community_grounding(stay=3000, food=1800):
        estimate = await estimate_bare_minimum_budget(_config())
    assert estimate["stay_community_based"] is True
    assert estimate["food_community_based"] is True
    # No dates given -> duration assumed at 5 days (4 nights), 2 adults, no
    # season multiplier (no start date known) -> stay = 3000*4*2 = 24000,
    # food = 1800*5*2 = 18000.
    assert estimate["breakdown"]["stay_inr"] == 24000
    assert estimate["breakdown"]["food_inr"] == 18000


async def test_hint_mentions_community_grounding_when_used():
    with community_grounding(stay=3000, food=1800):
        hint = await budget_estimate_prompt_hint(_config(origin=dict(BENGALURU)))
    assert "traveller-reported rates" in hint
    assert "traveller-reported spend" in hint


async def test_prebooked_accommodation_overrides_flat_and_community_estimate():
    with community_grounding(stay=3000, food=1800):
        estimate = await estimate_bare_minimum_budget(_config(prebooked_accommodation_inr=99999))
    assert estimate["breakdown"]["stay_inr"] == 99999
    assert estimate["accommodation_prebooked"] is True
