"""Per-day spend steering — "make day 3 cheaper".

Before this existed the refine LLM answered "I'll make a note to optimize Day 3"
with `action_type: "none"` and no config patch: nothing was stored, nothing
regenerated, and the promise was never kept (live-observed 2026-08-04). These
tests pin the three layers that make it real — a per-day cost that can move, a
structured constraint, and a prompt block that carries it.
"""
from __future__ import annotations

import pytest

from chains.chat_refine_chain import (
    ChatRefineResponse,
    _apply_day_cost_preference,
    _parse_day_cost_request,
)
from chains.itinerary_chain import (
    _coerce_cost_inr,
    _cost_correction_block,
    _cost_sanity_problem,
    _day_cost_guidance_block,
)
from models.itinerary import ItineraryDay, ItineraryItem, ItineraryItemLocation
from models.trip import DayCostPreference, DestinationInput, PinnedPOI, TripConfig


def _trip(days: int = 6, prefs: list[DayCostPreference] | None = None) -> TripConfig:
    return TripConfig(
        destination=DestinationInput(city="Bali", country="Indonesia"),
        dates={"start": "2026-09-10", "end": "2026-09-15", "duration_days": days},
        day_cost_preferences=prefs or [],
    )


def _item(cost: int, title: str = "Thing") -> ItineraryItem:
    return ItineraryItem(
        id=title, time_start="09:00", time_end="10:00", title=title,
        description="", location=ItineraryItemLocation(lat=0, lon=0),
        estimated_cost_inr=cost,
    )


class TestParseDayCostRequest:
    @pytest.mark.parametrize("text, expected", [
        ("make day 3 cheaper", (3, "cheaper")),
        ("Make Day 3 Cheaper", (3, "cheaper")),
        ("can we make day 2 less expensive?", (2, "cheaper")),
        ("day 4 on a budget please", (4, "cheaper")),
        ("the third day should be cheaper", (3, "cheaper")),
        ("let's save money on the second day", (2, "cheaper")),
        ("splurge on day 5", (5, "pricier")),
        ("day 1 should be luxurious", (1, "pricier")),
        ("make day 3 sasta", (3, "cheaper")),
    ])
    def test_recognised_requests(self, text, expected):
        assert _parse_day_cost_request(text, 6) == expected

    def test_last_day_resolves_against_trip_length(self):
        assert _parse_day_cost_request("make the last day cheaper", 6) == (6, "cheaper")

    def test_last_day_without_a_known_length_is_declined(self):
        """Guessing which day "last" means would re-cost an arbitrary day."""
        assert _parse_day_cost_request("make the last day cheaper", None) is None

    @pytest.mark.parametrize("text", [
        "make it cheaper",                 # no day — that's a trip-wide budget change
        "tell me about day 3",             # a day, but no spend direction
        "what's on day 2?",
        "make the pace relaxed",
        "",
    ])
    def test_non_requests_are_declined(self, text):
        assert _parse_day_cost_request(text, 6) is None

    def test_day_outside_the_trip_is_declined(self):
        """A 6-day trip has no day 9 — better to leave it to the LLM's reply
        than to silently re-cost a day the user cannot see."""
        assert _parse_day_cost_request("make day 9 cheaper", 6) is None

    def test_unknown_trip_length_still_accepts_an_explicit_day(self):
        assert _parse_day_cost_request("make day 3 cheaper", None) == (3, "cheaper")

    def test_pricier_wins_when_both_directions_appear(self):
        """"splurge on day 3, save elsewhere" — the named day is the splurge."""
        assert _parse_day_cost_request("splurge on day 3, save elsewhere", 6) == (3, "pricier")


class TestApplyDayCostPreference:
    def _resp(self) -> ChatRefineResponse:
        return ChatRefineResponse(reply="noted", action_type="none")

    def test_produces_a_real_config_patch(self):
        out = _apply_day_cost_preference(self._resp(), _trip(), "make day 3 cheaper")
        assert out.action_type == "patch_config"
        assert out.config_patch == {
            "day_cost_preferences": [{"day_number": 3, "direction": "cheaper"}]
        }

    def test_reply_no_longer_promises_a_future_edit(self):
        out = _apply_day_cost_preference(self._resp(), _trip(), "make day 3 cheaper")
        assert "day 3" in out.reply.lower()
        # The old failure mode, verbatim, must not come back.
        assert "make a note" not in out.reply.lower()
        assert "when i generate" not in out.reply.lower()

    def test_not_a_major_change_so_no_confirmation_modal(self):
        out = _apply_day_cost_preference(self._resp(), _trip(), "make day 3 cheaper")
        assert out.major_change is False

    def test_existing_preferences_are_preserved(self):
        trip = _trip(prefs=[DayCostPreference(day_number=1, direction="pricier")])
        out = _apply_day_cost_preference(self._resp(), trip, "make day 3 cheaper")
        assert out.config_patch["day_cost_preferences"] == [
            {"day_number": 1, "direction": "pricier"},
            {"day_number": 3, "direction": "cheaper"},
        ]

    def test_changing_your_mind_about_a_day_replaces_it(self):
        """Refinement is iterative — day 3 must not end up both cheaper and
        pricier, leaving the prompt to arbitrate."""
        trip = _trip(prefs=[DayCostPreference(day_number=3, direction="cheaper")])
        out = _apply_day_cost_preference(self._resp(), trip, "actually splurge on day 3")
        assert out.config_patch["day_cost_preferences"] == [
            {"day_number": 3, "direction": "pricier"}
        ]

    def test_unrelated_message_is_untouched(self):
        resp = self._resp()
        out = _apply_day_cost_preference(resp, _trip(), "what's the weather like?")
        assert out.action_type == "none"
        assert out.config_patch is None


class TestDayCostGuidanceBlock:
    def test_empty_without_preferences(self):
        assert _day_cost_guidance_block(_trip()) == ""

    def test_cheaper_block_names_the_day_and_the_levers(self):
        block = _day_cost_guidance_block(
            _trip(prefs=[DayCostPreference(day_number=3, direction="cheaper")])
        )
        assert "Day 3" in block
        assert "LESS" in block
        assert "street food" in block

    def test_pricier_block_is_the_mirror(self):
        block = _day_cost_guidance_block(
            _trip(prefs=[DayCostPreference(day_number=2, direction="pricier")])
        )
        assert "Day 2" in block and "SPEND MORE" in block

    def test_block_protects_pins_from_being_dropped_to_save_money(self):
        """The one way a cheaper day could silently break a hard constraint."""
        block = _day_cost_guidance_block(
            _trip(prefs=[DayCostPreference(day_number=3, direction="cheaper")])
        )
        assert "NEVER drop" in block

    def test_multiple_days_each_get_a_line(self):
        block = _day_cost_guidance_block(_trip(prefs=[
            DayCostPreference(day_number=1, direction="cheaper"),
            DayCostPreference(day_number=4, direction="pricier"),
        ]))
        assert "Day 1" in block and "Day 4" in block


class TestTripConfigValidation:
    def test_duplicate_days_collapse_last_write_wins(self):
        cfg = TripConfig(day_cost_preferences=[
            DayCostPreference(day_number=3, direction="cheaper"),
            DayCostPreference(day_number=3, direction="pricier"),
        ])
        assert cfg.day_cost_preferences == [
            DayCostPreference(day_number=3, direction="pricier")
        ]

    def test_preferences_are_ordered_by_day(self):
        cfg = TripConfig(day_cost_preferences=[
            DayCostPreference(day_number=5, direction="cheaper"),
            DayCostPreference(day_number=2, direction="cheaper"),
        ])
        assert [p.day_number for p in cfg.day_cost_preferences] == [2, 5]

    @pytest.mark.parametrize("day", [0, -1, 999])
    def test_impossible_day_numbers_are_rejected(self, day):
        with pytest.raises(Exception):
            DayCostPreference(day_number=day, direction="cheaper")

    def test_direction_is_a_closed_set(self):
        """The producer is our own parser, so a bad value is our bug — reject
        it rather than coercing and silently steering the wrong way."""
        with pytest.raises(Exception):
            DayCostPreference(day_number=1, direction="free")

    def test_defaults_to_empty_so_existing_configs_are_unaffected(self):
        assert TripConfig().day_cost_preferences == []


class TestDayCostRollup:
    def test_day_cost_is_the_sum_of_its_items(self):
        day = ItineraryDay(day_number=1, date="2026-09-10", theme="x",
                           items=[_item(500), _item(1200), _item(0)])
        assert day.estimated_cost_inr == 1700

    def test_empty_day_costs_nothing(self):
        assert ItineraryDay(day_number=1, date="", theme="").estimated_cost_inr == 0

    def test_rollup_follows_the_items_after_refinement(self):
        """A stored total would drift; a derived one cannot."""
        day = ItineraryDay(day_number=1, date="", theme="", items=[_item(900)])
        day.items.append(_item(100, "Extra"))
        assert day.estimated_cost_inr == 1000


class TestCostCoercion:
    """The model types this field loosely, and a ValidationError here would
    discard the ENTIRE itinerary over one cost estimate."""

    @pytest.mark.parametrize("raw, expected", [
        (500, 500),
        (500.7, 500),
        ("500", 500),
        ("₹500", 500),
        ("500 INR", 500),
        ("1,200", 1200),
        ("free", 0),
        ("", 0),
        (None, 0),
        (-50, 0),          # a negative cost is nonsense; the field would reject it
        (True, 0),         # bool is an int subclass — never a price
        ({"a": 1}, 0),
    ])
    def test_coercion(self, raw, expected):
        assert _coerce_cost_inr(raw) == expected


class TestPinsSurviveACheaperDay:
    def test_pins_and_day_costs_coexist_on_one_config(self):
        cfg = TripConfig(
            destination=DestinationInput(city="Bali"),
            pinned_pois=[PinnedPOI(name="Tanah Lot Temple", verified_by="osm")],
            day_cost_preferences=[DayCostPreference(day_number=3, direction="cheaper")],
        )
        assert cfg.pinned_pois[0].name == "Tanah Lot Temple"
        assert cfg.day_cost_preferences[0].day_number == 3


class TestCostSanityGuard:
    """Two live-observed failure modes (2026-08-05), both invisible to every
    other check because the itinerary is otherwise perfect — right day count,
    real places, pins honoured, internally consistent totals.

    A wrong number that looks like a number is the hardest kind to catch, and
    neither of these would have been caught by anything before this guard.
    """

    def _raw(self, total: int, day_costs: dict[int, int] | None = None) -> dict:
        day_costs = day_costs or {1: 2000, 2: 2000, 3: 2000}
        return {
            "expense_breakdown": {"total_inr": total},
            "days": [
                {"day_number": d, "items": [{"estimated_cost_inr": c}]}
                for d, c in sorted(day_costs.items())
            ],
        }

    def test_sane_costs_pass(self):
        assert _cost_sanity_problem(self._raw(176_225), _trip()) is None

    def test_wrong_currency_is_caught(self):
        """The real one: Rs 124,525,000 for 2 people over 6 days, because
        Gemini costed in Indonesian Rupiah."""
        problem = _cost_sanity_problem(self._raw(124_525_000), _trip())
        assert problem is not None
        assert "local currency" in problem

    def test_absurdly_low_total_is_caught(self):
        problem = _cost_sanity_problem(self._raw(500), _trip())
        assert problem is not None and "too low" in problem

    def test_an_expensive_but_real_trip_is_not_flagged(self):
        """A luxury trip must not trip a unit-error detector."""
        assert _cost_sanity_problem(self._raw(1_200_000), _trip()) is None

    def test_cheaper_day_that_is_not_cheaper_is_caught(self):
        """The user's point: a cost that moves the WRONG WAY is a calculation
        failure even when the scale looks perfectly normal."""
        trip = _trip(prefs=[DayCostPreference(day_number=3, direction="cheaper")])
        raw = self._raw(150_000, {1: 2000, 2: 2000, 3: 9000})
        problem = _cost_sanity_problem(raw, trip)
        assert problem is not None
        assert "CHEAPER" in problem and "day 3" in problem

    def test_cheaper_day_that_is_cheaper_passes(self):
        trip = _trip(prefs=[DayCostPreference(day_number=3, direction="cheaper")])
        raw = self._raw(150_000, {1: 4000, 2: 4000, 3: 1200})
        assert _cost_sanity_problem(raw, trip) is None

    def test_pricier_day_that_is_not_pricier_is_caught(self):
        trip = _trip(prefs=[DayCostPreference(day_number=2, direction="pricier")])
        raw = self._raw(150_000, {1: 5000, 2: 1000, 3: 5000})
        problem = _cost_sanity_problem(raw, trip)
        assert problem is not None and "SPEND MORE" in problem

    def test_all_zero_day_costs_do_not_trigger_a_direction_failure(self):
        """A model that omitted per-item costs entirely is a different problem;
        flagging it as a direction violation would send a misleading correction."""
        trip = _trip(prefs=[DayCostPreference(day_number=3, direction="cheaper")])
        raw = self._raw(150_000, {1: 0, 2: 0, 3: 0})
        assert _cost_sanity_problem(raw, trip) is None

    def test_group_size_scales_the_plausible_ceiling(self):
        """The same total is fine for a big group and absurd for a solo
        traveller — the check is per person per day, not absolute."""
        big = TripConfig(
            dates={"start": "2026-09-10", "end": "2026-09-15", "duration_days": 6},
            group={"adults": 8},
        )
        solo = TripConfig(
            dates={"start": "2026-09-10", "end": "2026-09-15", "duration_days": 6},
            group={"adults": 1},
        )
        raw = self._raw(9_000_000)
        assert _cost_sanity_problem(raw, big) is None
        assert _cost_sanity_problem(raw, solo) is not None

    def test_missing_breakdown_is_not_flagged_as_a_cost_error(self):
        assert _cost_sanity_problem({"days": []}, _trip()) is None


class TestCostCorrectionBlock:
    def test_correction_names_the_defect_and_anchors_the_currency(self):
        block = _cost_correction_block("the total came to INR 124,525,000")
        assert "INDIAN RUPEES (INR)" in block
        assert "124,525,000" in block

    def test_correction_preserves_the_plan(self):
        """Only the costs were wrong — re-rolling the places would throw away
        verified pins and a good itinerary to fix a number."""
        block = _cost_correction_block("x")
        assert "same pinned" in block and "only the costs were wrong" in block
