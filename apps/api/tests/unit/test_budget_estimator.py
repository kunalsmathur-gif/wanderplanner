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
from contextlib import contextmanager
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
    """Default: simulate "the corpus has nothing for this destination" so
    these tests are deterministic. Tests that want the grounded path override
    this via `community_grounding(...)`.

    Both entry points must be patched. Only `community_median_price_inr` was
    stubbed here originally — food went through the same function back then —
    but v10.38.0 split food onto `community_food_per_day_inr`, and that one
    was left reaching the *live* Qdrant Cloud cluster. It stayed green purely
    because the corpus was empty; the first real YouTube ingestion (2026-07-25,
    11,838 comments) gave Colombo genuine food signal and
    `test_stay_and_food_fall_back_to_flat_tier_when_corpus_empty` started
    failing on `food_community_based is True`. A unit test must not depend on
    what happens to be in a shared cloud database.
    """
    with patch(
        "core.budget_estimator.community_median_price_inr", new=AsyncMock(return_value=None)
    ), patch(
        "core.budget_estimator.community_food_per_day_inr", new=AsyncMock(return_value=(None, False))
    ):
        yield


def community_grounding(
    *, stay: float | None = None, food: float | None = None, food_directly_observed: bool = False
):
    """Returns a context manager patching both grounding entry points: stay
    goes through `community_median_price_inr`, food through
    `community_food_per_day_inr` (which additionally reports whether the figure
    was directly observed as a daily rate — see core/price_extraction.py::
    food_per_day_estimate_inr).

    `food_directly_observed=False` (the default) models the reconciled
    per-meal path, which stays subject to the flat-value floor."""

    def _fake_stay(dest_city, query_suffix, low, high, min_samples=2, limit=5,
                   context_keywords=None):
        if "hotel" in query_suffix or "accommodation" in query_suffix:
            return stay
        return None

    def _fake_food(dest_city, query_suffix, low, high, min_samples=2, limit=5,
                   context_keywords=None, meals_per_day=3.0):
        return food, food_directly_observed

    @contextmanager
    def _both():
        with patch(
            "core.budget_estimator.community_median_price_inr", new=AsyncMock(side_effect=_fake_stay)
        ), patch(
            "core.budget_estimator.community_food_per_day_inr", new=AsyncMock(side_effect=_fake_food)
        ):
            yield

    return _both()


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


# ── Domestic (India) rail/bus/cab "cheaper alternative" call-out ──────────

DELHI = {"city": "Delhi", "country": "India", "lat": 28.6139, "lon": 77.2090}
GOA = {"city": "Goa", "country": "India", "lat": 15.2993, "lon": 74.1240}


async def test_domestic_route_with_real_savings_surfaces_cheaper_alternative():
    config = _config(
        scope="domestic", origin=dict(DELHI), destination=dict(GOA), group={"adults": 2},
    )
    estimate = await estimate_bare_minimum_budget(config)
    alt = estimate["cheaper_alternative"]
    assert alt is not None
    assert alt["mode"] in {"rail", "bus", "cab"}
    assert alt["fare_inr"] > 0
    assert alt["savings_fraction"] >= 0.15


async def test_international_route_never_surfaces_cheaper_alternative():
    # Same coordinates, but scope left as the default "international" — the
    # rail/bus/cab alternative must never fire for a non-domestic route.
    config = _config(origin=dict(DELHI), destination=dict(GOA), group={"adults": 2})
    estimate = await estimate_bare_minimum_budget(config)
    assert estimate["cheaper_alternative"] is None


async def test_domestic_route_without_coords_does_not_crash_and_has_no_alternative():
    # scope="domestic" but no lat/lon on one side (not yet geocoded) — must
    # degrade gracefully, not raise or fabricate a distance.
    config = _config(
        scope="domestic",
        origin={"city": "Delhi"},
        destination={"city": "Goa", "country": "India"},
        group={"adults": 2},
    )
    estimate = await estimate_bare_minimum_budget(config)
    assert estimate["cheaper_alternative"] is None


async def test_cheaper_alternative_note_appears_in_the_prompt_hint():
    config = _config(scope="domestic", origin=dict(DELHI), destination=dict(GOA), group={"adults": 2})
    hint = await budget_estimate_prompt_hint(config)
    assert "CHEAPER ALTERNATIVE AVAILABLE" in hint


async def test_no_cheaper_alternative_note_for_international_route():
    config = _config(origin=dict(DELHI), destination=dict(GOA), group={"adults": 2})
    hint = await budget_estimate_prompt_hint(config)
    assert "CHEAPER ALTERNATIVE AVAILABLE" not in hint
