"""Entry/visa cost is excluded from every estimate, structurally.

🔴 Reported from production: a 5-day Bhutan trip showed ₹41,000 of "visa". That
is the international Sustainable Development Fee (USD 100/night) converted to
INR — for a traveller who needs no visa for Bhutan at all and pays an SDF of
₹1,200/night. Wrong rate, wrong label, delivered with the same confidence as a
real figure.

The number was never looked up. `visa_inr` was a free slot in the prompt, so it
came from the model's recollection, while the visa corpus this project scrapes
and refreshes on a schedule went unread by both chains that produce it.

Product decision: a missing line the traveller knows to check beats a confident
wrong number they budget against. That cannot be delivered by a prompt rule —
an LLM has no calibrated sense of when it is guessing — so the exclusion is
enforced in code and the prompts merely agree with it. These tests pin the
enforcement, not the prompt.
"""
from __future__ import annotations

from chains.feasibility_chain import _mock_feasibility
from chains.itinerary_chain import _parse_expense_breakdown
from models.trip import TripConfig


class TestItineraryBreakdown:
    def test_visa_is_zero_even_when_the_model_supplies_a_figure(self):
        raw = {
            "flights_inr": 40000,
            "visa_inr": 41000,  # the reported Bhutan number
            "accommodation_inr": 30000,
            "activities_inr": 5000,
            "food_inr": 10000,
            "local_transport_inr": 3000,
            "shopping_inr": 2000,
        }

        breakdown = _parse_expense_breakdown(raw, TripConfig())

        assert breakdown.visa_inr == 0

    def test_the_excluded_figure_is_not_folded_into_the_total(self):
        # Dropping the line but keeping the money in `total_inr` would be the
        # worst of both: still wrong, and now invisible.
        raw = {"flights_inr": 40000, "visa_inr": 41000, "accommodation_inr": 30000}

        breakdown = _parse_expense_breakdown(raw, TripConfig())

        assert breakdown.total_inr < 41000 + 40000 + 30000

    def test_the_other_lines_are_untouched(self):
        raw = {
            "flights_inr": 40000,
            "visa_inr": 41000,
            "accommodation_inr": 30000,
            "activities_inr": 5000,
            "food_inr": 10000,
            "local_transport_inr": 3000,
            "shopping_inr": 2000,
        }

        breakdown = _parse_expense_breakdown(raw, TripConfig())

        assert breakdown.flights_inr == 40000
        assert breakdown.accommodation_inr == 30000
        assert breakdown.food_inr == 10000

    def test_a_missing_visa_key_is_still_zero(self):
        breakdown = _parse_expense_breakdown({"flights_inr": 40000}, TripConfig())
        assert breakdown.visa_inr == 0


class TestFeasibilityMock:
    def test_the_mock_path_shows_no_visa_figure_either(self):
        # The mock previously charged a flat ₹6,500/person. Left alone it would
        # be the one surface still showing a number production never produces,
        # so dev and eval runs would validate behaviour that does not ship.
        result = _mock_feasibility({"nights": 4, "total_people": 2}, budget_inr=200000)

        assert result.breakdown.visa_inr == 0
