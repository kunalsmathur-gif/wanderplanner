"""Unit tests for the budget-recommendation comparison eval's scoring
module (docs/eval-set.md Section 14, item 5/10 follow-up on
docs/NEXT_SESSION_TODO.md). Pure-function tests, no live LLM calls — same
"fully offline" pattern as test_data_completeness_check.py; the runner
itself is what's meant to be run for real against production model APIs.
"""
from __future__ import annotations

from eval.budget_comparison_scoring import (
    aggregate_model,
    anchor_adherence,
    asked_clarifying_question,
    coefficient_of_variation,
    extract_total_inr,
    gave_breakdown,
    score_one_response,
    used_hedge_language,
)


class TestExtractTotalInr:
    def test_explicit_total_line_preferred_over_other_amounts(self):
        text = (
            "Flights: roughly INR 40,000 per person.\n"
            "Hotel: about INR 3,500/night.\n"
            "Total estimated budget: INR 85,000 for both of you."
        )
        assert extract_total_inr(text) == 85_000

    def test_falls_back_to_largest_plausible_amount_when_no_total_line(self):
        text = "You might spend around $500 on flights and $150 on food per day."
        # $500 -> 43,500 INR is the largest plausible figure found.
        assert extract_total_inr(text) == 43_500.0

    def test_handles_lakh_suffix(self):
        text = "Overall, plan for a total of INR 1.5 lakh for the trip."
        assert extract_total_inr(text) == 150_000.0

    def test_handles_k_suffix(self):
        text = "Total budget: INR 85k should cover it."
        assert extract_total_inr(text) == 85_000.0

    def test_converts_foreign_currency_symbols(self):
        text = "Total: around €900 for the whole trip."
        assert extract_total_inr(text) == 900 * 93.0

    def test_returns_none_when_no_amount_present(self):
        text = "I'd need to know your departure city and travel dates before I can estimate anything."
        assert extract_total_inr(text) is None

    def test_discards_implausible_out_of_bounds_amounts(self):
        # A lone "$2" (e.g. "a $2 coffee") shouldn't be read as a trip total.
        text = "You'll probably grab a $2 coffee most mornings."
        assert extract_total_inr(text) is None


class TestBehaviouralChecks:
    def test_detects_clarifying_question(self):
        text = "Before I can give you an estimate, how many people are travelling and which city are you flying from?"
        assert asked_clarifying_question(text) is True

    def test_no_clarifying_question_when_answer_given_directly(self):
        text = "Based on your trip, I'd budget around INR 80,000 total for flights, stay, and food."
        assert asked_clarifying_question(text) is False

    def test_gave_breakdown_true_with_two_or_more_categories(self):
        text = "Flights will cost about INR 40,000 and hotels around INR 20,000 for the trip."
        assert gave_breakdown(text) is True

    def test_gave_breakdown_false_with_single_bare_number(self):
        text = "You should budget around INR 80,000 total for the trip."
        assert gave_breakdown(text) is False

    def test_hedge_language_detected(self):
        text = "This is approximately INR 80,000, though it can vary depending on the season."
        assert used_hedge_language(text) is True

    def test_hedge_language_absent_for_confident_bare_claim(self):
        text = "Your total budget is INR 80,000."
        assert used_hedge_language(text) is False


class TestAnchorAdherence:
    def test_within_range_scores_full_credit(self):
        assert anchor_adherence(70_000, 60_000, 80_000) == 1.0

    def test_no_answer_scores_zero(self):
        assert anchor_adherence(None, 60_000, 80_000) == 0.0

    def test_below_range_decays_toward_zero(self):
        score = anchor_adherence(30_000, 60_000, 80_000)
        assert 0.0 < score < 1.0
        assert score == 0.5  # 30,000 / 60,000

    def test_above_range_decays_to_zero_by_2x_high_bound(self):
        assert anchor_adherence(160_000, 60_000, 80_000) == 0.0  # exactly 2x the high bound
        mid_overshoot = anchor_adherence(120_000, 60_000, 80_000)
        assert 0.0 < mid_overshoot < 1.0


class TestCoefficientOfVariation:
    def test_zero_variance_for_identical_values(self):
        assert coefficient_of_variation([80_000, 80_000, 80_000]) == 0.0

    def test_positive_variance_for_differing_values(self):
        cv = coefficient_of_variation([70_000, 80_000, 90_000])
        assert cv is not None
        assert cv > 0.0

    def test_none_with_fewer_than_two_values(self):
        assert coefficient_of_variation([80_000]) is None
        assert coefficient_of_variation([]) is None

    def test_ignores_none_values(self):
        cv = coefficient_of_variation([80_000, None, 80_000])
        assert cv == 0.0


class TestScoreOneResponse:
    def test_full_scoring_shape(self):
        text = "Total estimated budget: INR 75,000 for flights, hotel, and food, though prices can vary."
        result = score_one_response(text, 60_000, 80_000)
        assert result["extracted_total_inr"] == 75_000
        assert result["anchor_adherence"] == 1.0
        assert result["asked_clarifying_question"] is False
        assert result["gave_breakdown"] is True
        assert result["used_hedge_language"] is True


class TestAggregateModel:
    def test_aggregates_across_successful_calls(self):
        results = [
            {"error": None, "extracted_total_inr": 75_000, "anchor_adherence": 1.0,
             "asked_clarifying_question": False, "gave_breakdown": True, "used_hedge_language": True,
             "latency_ms": 500.0, "cost_usd": 0.001},
            {"error": None, "extracted_total_inr": None, "anchor_adherence": 0.0,
             "asked_clarifying_question": True, "gave_breakdown": False, "used_hedge_language": False,
             "latency_ms": 600.0, "cost_usd": 0.001},
        ]
        summary = aggregate_model(results)
        assert summary["calls"] == 2
        assert summary["errors"] == 0
        assert summary["no_answer_rate"] == 0.5
        assert summary["anchor_adherence_mean"] == 0.5
        assert summary["clarifying_question_rate"] == 0.5
        assert summary["breakdown_rate"] == 0.5

    def test_all_errored_returns_error_summary(self):
        results = [{"error": "boom", "latency_ms": 0}]
        summary = aggregate_model(results)
        assert summary["errors"] == 1
        assert summary["error_rate"] == 1.0
        assert "anchor_adherence_mean" not in summary
