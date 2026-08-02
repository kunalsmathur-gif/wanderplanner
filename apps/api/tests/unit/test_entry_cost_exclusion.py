"""A visa figure is shown only when the corpus actually covered the country.

🔴 Reported from production: a 5-day Bhutan trip showed ₹41,000 of "visa". That
is the international Sustainable Development Fee (USD 100/night) converted to
INR — for a traveller who needs no visa for Bhutan at all and pays an SDF of
₹1,200/night. Wrong rate, wrong label, delivered with the same confidence as a
real figure.

The number was never looked up. `visa_inr` was a free slot in the prompt, so it
came from the model's recollection, while the visa corpus this project scrapes
and refreshes went unread by both chains that produce it.

The contract is three-way, and the distinction between the last two is the
whole point:

  covered      -> show the figure, even if the source is dated
  not covered  -> None, rendered "not available"
  genuinely 0  -> 0, meaning entry really is free

Collapsing "unknown" into 0 would trade a wrong number for a wrong claim. It
cannot be delivered by a prompt rule either — an LLM has no calibrated sense of
when it is guessing — so the gate is structural and these tests pin the gate,
not the prompt.
"""
from __future__ import annotations

from chains.feasibility_chain import _build_response, _mock_feasibility
from chains.itinerary_chain import _parse_expense_breakdown
from models.trip import TripConfig

_RAW = {
    "flights_inr": 40000,
    "visa_inr": 41000,  # the reported Bhutan number
    "accommodation_inr": 30000,
    "activities_inr": 5000,
    "food_inr": 10000,
    "local_transport_inr": 3000,
    "shopping_inr": 2000,
}


class TestItineraryBreakdown:
    def test_ungrounded_visa_is_none_not_zero(self):
        # None means "we could not look this up". 0 would claim entry is free,
        # which is a different lie from the one being fixed.
        breakdown = _parse_expense_breakdown(_RAW, TripConfig(), entry_grounded=False)

        assert breakdown.visa_inr is None

    def test_grounded_visa_is_kept(self):
        # Covered country: the figure is priced against real retrieved rules,
        # so it ships — a dated real number beats a blank where a cost exists.
        breakdown = _parse_expense_breakdown(_RAW, TripConfig(), entry_grounded=True)

        assert breakdown.visa_inr == 41000

    def test_a_grounded_zero_survives_as_zero(self):
        # Visa-free destinations must still be able to say "free" — that is a
        # real answer, and suppressing it would be its own inaccuracy.
        raw = {**_RAW, "visa_inr": 0}
        breakdown = _parse_expense_breakdown(raw, TripConfig(), entry_grounded=True)

        assert breakdown.visa_inr == 0

    def test_an_unknown_entry_cost_contributes_nothing_to_the_total(self):
        # Keeping the money in `total_inr` while dropping the line would be the
        # worst outcome: still wrong, and now invisible.
        grounded = _parse_expense_breakdown(_RAW, TripConfig(), entry_grounded=True)
        ungrounded = _parse_expense_breakdown(_RAW, TripConfig(), entry_grounded=False)

        assert ungrounded.total_inr < grounded.total_inr

    def test_the_other_lines_are_untouched_either_way(self):
        breakdown = _parse_expense_breakdown(_RAW, TripConfig(), entry_grounded=False)

        assert breakdown.flights_inr == 40000
        assert breakdown.accommodation_inr == 30000
        assert breakdown.food_inr == 10000

    def test_defaults_to_ungrounded(self):
        # A caller that forgets the flag must fail closed, not leak a guess.
        assert _parse_expense_breakdown(_RAW, TripConfig()).visa_inr is None


class TestFeasibilityBreakdown:
    def test_ungrounded_visa_is_none(self):
        result = _build_response(
            {"flights_inr": 40000, "visa_inr": 41000, "total_estimated_inr": 100000},
            budget_inr=200000,
            entry_grounded=False,
        )

        assert result.breakdown.visa_inr is None

    def test_grounded_visa_is_kept(self):
        result = _build_response(
            {"flights_inr": 40000, "visa_inr": 6000, "total_estimated_inr": 100000},
            budget_inr=200000,
            entry_grounded=True,
        )

        assert result.breakdown.visa_inr == 6000

    def test_the_mock_path_reports_unknown_rather_than_a_flat_fee(self):
        # The mock previously charged ₹6,500/person unconditionally. It runs
        # with no corpus behind it, so "unknown" is what production would say.
        result = _mock_feasibility({"nights": 4, "total_people": 2}, budget_inr=200000)

        assert result.breakdown.visa_inr is None
