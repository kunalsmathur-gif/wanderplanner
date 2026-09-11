"""Repeated feasibility checks against an unchanged trip must return a
stable estimate.

🔴 Reported from production: a single wizard session saw the "estimated
minimum" escalate three times in a row (₹325,450 -> ₹434,300 -> ₹510,300)
purely from the user re-checking after raising the budget to match the
previous verdict, with no destination/dates/group/itinerary change in
between. `budget_inr` was already excluded from the Gemini prompt (the
2f347ee fix for the anchoring loop), so the model was never shown the
budget it could anchor on — but nothing stopped it from independently
resampling a fresh (and, per the prompt's own "lean slightly higher"
instruction, upward-biased) guess on every retry, since each check was a
brand new LLM call with no memory of the last one.

These tests pin two independent fixes for the same user-visible symptom:

1. `_estimate_cache_key` / `_cached_estimate` / `_store_estimate`: the raw
   LLM JSON is now cached per unique (trip-minus-budget) signature, so a
   retry against the same trip returns the exact same numbers instead of a
   fresh, possibly-different sample.
2. `_build_response`: when the deterministic bare-minimum floor replaces
   the LLM's total, the displayed flights/accommodation/food line items now
   come from that same floor breakdown too, instead of leaving stale LLM
   figures next to a floor-driven total that didn't actually sum to them.
"""
from __future__ import annotations

from chains.feasibility_chain import (
    _ESTIMATE_CACHE,
    _build_response,
    _cached_estimate,
    _estimate_cache_key,
    _store_estimate,
)
from models.trip import TripConfig

_RAW = {
    "flights_inr": 40000,
    "visa_inr": 0,
    "accommodation_inr": 30000,
    "daily_expenses_inr": 10000,
    "total_estimated_inr": 80000,
}


class TestEstimateCache:
    def setup_method(self):
        _ESTIMATE_CACHE.clear()

    def teardown_method(self):
        _ESTIMATE_CACHE.clear()

    def test_identical_inputs_produce_the_same_key(self):
        summary = {"destination": "Bali", "nights": 6, "total_people": 4}
        key_a = _estimate_cache_key(summary, "BUDGET TIER GUIDANCE: mid-range tier.", "")
        key_b = _estimate_cache_key(dict(summary), "BUDGET TIER GUIDANCE: mid-range tier.", "")
        assert key_a == key_b

    def test_a_changed_trip_produces_a_different_key(self):
        # Budget is deliberately never part of the signature (it's excluded
        # from the prompt entirely), but a real trip change (more nights)
        # must still bust the cache.
        summary = {"destination": "Bali", "nights": 6, "total_people": 4}
        changed = {"destination": "Bali", "nights": 10, "total_people": 4}
        key_a = _estimate_cache_key(summary, "hint", "")
        key_b = _estimate_cache_key(changed, "hint", "")
        assert key_a != key_b

    def test_cache_roundtrip_returns_the_stored_value(self):
        key = _estimate_cache_key({"destination": "Bali"}, "hint", "")
        payload = {"data": _RAW, "entry_grounded": False}
        _store_estimate(key, payload)

        assert _cached_estimate(key) == payload

    def test_cache_miss_returns_none(self):
        assert _cached_estimate("no-such-key") is None

    def test_expired_entries_are_evicted_on_read(self):
        key = _estimate_cache_key({"destination": "Bali"}, "hint", "")
        _store_estimate(key, {"data": _RAW, "entry_grounded": False})
        # Simulate the cache entry having been written long enough ago to
        # have expired, without waiting on a real clock in the test.
        data, _cached_at = _ESTIMATE_CACHE[key]
        _ESTIMATE_CACHE[key] = (data, -10_000.0)

        assert _cached_estimate(key) is None
        assert key not in _ESTIMATE_CACHE


class TestFloorBreakdownConsistency:
    def test_floor_breakdown_replaces_stale_llm_line_items(self):
        # The LLM's own guess (₹80,000 total) undershoots the deterministic
        # floor (₹150,000) -- previously `total_estimated_inr` alone would
        # jump to the floor while flights/accommodation/food kept showing
        # the LLM's now-superseded ₹40k/₹30k/₹10k, which never summed to
        # ₹150,000 next to them.
        bare_minimum = {
            "total_inr": 150000,
            "breakdown": {"flights_inr": 90000, "stay_inr": 40000, "food_inr": 20000},
        }
        response = _build_response(_RAW, budget_inr=100000, bare_minimum=bare_minimum, trip_config=TripConfig())

        assert response.breakdown.total_estimated_inr == 150000
        assert response.breakdown.flights_inr == 90000
        assert response.breakdown.accommodation_inr == 40000
        assert response.breakdown.daily_expenses_inr == 20000

    def test_llm_line_items_are_kept_when_the_floor_is_not_binding(self):
        # LLM total (₹80,000) already exceeds the floor (₹50,000) -- the
        # floor never kicks in, so the original LLM figures must be
        # untouched.
        bare_minimum = {
            "total_inr": 50000,
            "breakdown": {"flights_inr": 20000, "stay_inr": 20000, "food_inr": 10000},
        }
        response = _build_response(_RAW, budget_inr=100000, bare_minimum=bare_minimum, trip_config=TripConfig())

        assert response.breakdown.total_estimated_inr == 80000
        assert response.breakdown.flights_inr == 40000
        assert response.breakdown.accommodation_inr == 30000
        assert response.breakdown.daily_expenses_inr == 10000

    def test_prebooked_flights_survive_the_floor_swap(self):
        # A user's real, already-paid flight cost is a sunk cost that must
        # never be silently overwritten by the floor's heuristic guess, even
        # when the floor is otherwise binding for accommodation/food.
        bare_minimum = {
            "total_inr": 150000,
            "breakdown": {"flights_inr": 90000, "stay_inr": 40000, "food_inr": 20000},
        }
        trip_config = TripConfig(prebooked_flights_inr=55000)
        response = _build_response(_RAW, budget_inr=100000, bare_minimum=bare_minimum, trip_config=trip_config)

        assert response.breakdown.flights_inr == 55000
        assert response.breakdown.accommodation_inr == 40000


class TestCeilingCapsAnOverGenerousLlmGuess:
    """Live prod bug (2026-09-11): a feasibility check quoted ₹114,650 as the
    minimum needed, but the itinerary the user actually generated afterwards
    came to only ₹81,785 — a ~40% gap. The floor (`_build_response`'s
    existing bare-minimum-floor swap) only guards against the LLM guessing
    too LOW; nothing previously guarded the opposite direction. These tests
    pin the new ceiling: the LLM's total is capped at
    `_CEILING_OVER_FLOOR_MULTIPLIER`x the deterministic floor, and the
    displayed line items are scaled down consistently so they still sum to
    the (now-capped) total shown next to them."""

    def test_a_wildly_inflated_llm_total_is_capped_at_the_ceiling(self):
        # Floor is ₹50,000; ceiling is 2x that = ₹100,000. An LLM total of
        # ₹300,000 (6x the floor) is far past "legitimately pricier" and
        # must be capped down to the ceiling.
        raw = {**_RAW, "total_estimated_inr": 300000, "flights_inr": 150000,
               "accommodation_inr": 100000, "daily_expenses_inr": 50000, "visa_inr": 0}
        bare_minimum = {
            "total_inr": 50000,
            "breakdown": {"flights_inr": 20000, "stay_inr": 20000, "food_inr": 10000},
        }
        response = _build_response(raw, budget_inr=100000, bare_minimum=bare_minimum, trip_config=TripConfig())

        assert response.breakdown.total_estimated_inr == 100000
        # Line items must still sum to the capped total, not silently drift.
        assert (
            response.breakdown.flights_inr
            + response.breakdown.accommodation_inr
            + response.breakdown.daily_expenses_inr
        ) == 100000

    def test_a_moderately_higher_llm_total_within_the_ceiling_is_untouched(self):
        # 1.6x the floor is inside the 2x ceiling -- a legitimately pricier
        # (e.g. mid-range hotel) guess must survive untouched.
        raw = {**_RAW, "total_estimated_inr": 80000}
        bare_minimum = {
            "total_inr": 50000,
            "breakdown": {"flights_inr": 20000, "stay_inr": 20000, "food_inr": 10000},
        }
        response = _build_response(raw, budget_inr=100000, bare_minimum=bare_minimum, trip_config=TripConfig())

        assert response.breakdown.total_estimated_inr == 80000
        assert response.breakdown.flights_inr == 40000

    def test_ceiling_never_fights_the_floor(self):
        # When the floor is binding (LLM total below the floor), the floor
        # path already sets total == bare_minimum_inr, which the ceiling
        # (>= the floor by construction) must never re-cap or fight with.
        raw = {**_RAW, "total_estimated_inr": 30000, "flights_inr": 15000,
               "accommodation_inr": 10000, "daily_expenses_inr": 5000, "visa_inr": 0}
        bare_minimum = {
            "total_inr": 150000,
            "breakdown": {"flights_inr": 90000, "stay_inr": 40000, "food_inr": 20000},
        }
        response = _build_response(raw, budget_inr=200000, bare_minimum=bare_minimum, trip_config=TripConfig())

        assert response.breakdown.total_estimated_inr == 150000

    def test_prebooked_flights_are_not_scaled_down_by_the_ceiling(self):
        # A user's real, already-paid flight cost must survive the ceiling
        # cap untouched, exactly like it already survives the floor swap --
        # it's a sunk cost, not a guess to be adjusted either way.
        raw = {**_RAW, "total_estimated_inr": 300000, "flights_inr": 150000,
               "accommodation_inr": 100000, "daily_expenses_inr": 50000, "visa_inr": 0}
        bare_minimum = {
            "total_inr": 50000,
            "breakdown": {"flights_inr": 20000, "stay_inr": 20000, "food_inr": 10000},
        }
        trip_config = TripConfig(prebooked_flights_inr=60000)
        response = _build_response(raw, budget_inr=100000, bare_minimum=bare_minimum, trip_config=trip_config)

        assert response.breakdown.flights_inr == 60000
        # Total is still capped at the ceiling overall.
        assert response.breakdown.total_estimated_inr == 100000
