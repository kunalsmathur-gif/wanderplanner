"""Tests for core/price_extraction.py — deterministic (no-LLM) INR price
extraction from free-text community snippets."""
from core.price_extraction import (
    FOOD_CONTEXT_KEYWORDS,
    STAY_CONTEXT_KEYWORDS,
    extract_price_mentions_inr,
    food_per_day_estimate_inr,
    has_price_mention,
    median_price_inr,
    price_focused_excerpt,
)

STAY_BOUNDS = (300, 50_000)


def test_extracts_inr_symbol_amount():
    amounts = extract_price_mentions_inr(["Paid ₹4500 for the night, was decent."], *STAY_BOUNDS)
    assert amounts == [4500.0]


def test_extracts_and_converts_usd_amount():
    amounts = extract_price_mentions_inr(["Room was $40/night, clean and central."], *STAY_BOUNDS)
    assert amounts == [40.0 * 83.0]


def test_extracts_lkr_amount_with_correct_conversion():
    amounts = extract_price_mentions_inr(["Guesthouse charged LKR 8000 per night."], *STAY_BOUNDS)
    assert amounts == [8000 * 0.28]


def test_discards_amounts_outside_bounds():
    # A $500,000 mention should never be read as a nightly hotel rate.
    amounts = extract_price_mentions_inr(["Saw a house listed for $500,000 nearby."], *STAY_BOUNDS)
    assert amounts == []


def test_handles_comma_thousands_separator():
    amounts = extract_price_mentions_inr(["Total trip cost was ₹45,000 for the week."], 1000, 100_000)
    assert amounts == [45000.0]


def test_median_returns_none_below_min_samples():
    snippets = ["Paid ₹4500 for one night."]
    assert median_price_inr(snippets, *STAY_BOUNDS, min_samples=2) is None


def test_median_returns_value_once_enough_samples():
    snippets = [
        "Paid ₹4500 for the night, first hotel.",
        "Second place was ₹5000 a night, nicer.",
        "Third one was cheaper at ₹4000/night.",
    ]
    assert median_price_inr(snippets, *STAY_BOUNDS, min_samples=2) == 4500.0


def test_unrecognised_currency_symbol_ignored():
    amounts = extract_price_mentions_inr(["Cost about 5000 baht for the week."], *STAY_BOUNDS)
    assert amounts == []


# --- Bare-number (no currency symbol) extraction, added 2026-07-21 for
# casual YouTube comments (e.g. "Choki dani 700 per person") ---

FOOD_BOUNDS = (50, 5000)


def test_extracts_bare_amount_with_per_person_suffix():
    amounts = extract_price_mentions_inr(["Choki dani 700 per person"], *FOOD_BOUNDS)
    assert amounts == [700.0]


def test_extracts_bare_amount_with_pp_suffix():
    amounts = extract_price_mentions_inr(["Thali was 250pp, great value."], *FOOD_BOUNDS)
    assert amounts == [250.0]


def test_extracts_bare_amount_with_per_night_suffix():
    amounts = extract_price_mentions_inr(["Got a room for 1200 per night near the fort."], STAY_BOUNDS[0], STAY_BOUNDS[1])
    assert amounts == [1200.0]


def test_extracts_bare_amount_after_price_verb():
    amounts = extract_price_mentions_inr(["paid 500 for the whole taxi ride"], *FOOD_BOUNDS)
    assert amounts == [500.0]


def test_extracts_bare_amount_after_cost_verb_with_words_between():
    amounts = extract_price_mentions_inr(["the total cost was around 900 for two"], *FOOD_BOUNDS)
    assert amounts == [900.0]


def test_bare_number_with_no_price_context_is_ignored():
    # "Tapri central 200" has no unit/verb anchor — genuinely ambiguous,
    # correctly left unextracted rather than guessed.
    amounts = extract_price_mentions_inr(["Tapri central 200"], *FOOD_BOUNDS)
    assert amounts == []


def test_timestamp_like_number_not_misread_as_price():
    amounts = extract_price_mentions_inr(["Skip to 10:30 for the food market segment"], *FOOD_BOUNDS)
    assert amounts == []


def test_view_count_not_misread_as_price():
    amounts = extract_price_mentions_inr(["This video has 700 views already"], *FOOD_BOUNDS)
    assert amounts == []


def test_phone_number_like_digits_not_misread_as_price():
    amounts = extract_price_mentions_inr(["call the guide at 98765 for details"], *FOOD_BOUNDS)
    assert amounts == []


def test_symbol_amount_not_double_counted_with_bare_pass():
    # "₹700 per person" must be counted once (via the symbol pass), not
    # again via the bare-number unit-suffix pass on the same text.
    amounts = extract_price_mentions_inr(["₹700 per person for the buffet"], *FOOD_BOUNDS)
    assert amounts == [700.0]


def test_bare_amount_respects_bounds():
    amounts = extract_price_mentions_inr(["paid 5000000 per person, absurd scam price"], *FOOD_BOUNDS)
    assert amounts == []


def test_median_uses_mixed_symbol_and_bare_amounts():
    snippets = [
        "Choki dani 700 per person, worth it",
        "Another thali place was ₹650 per person",
        "Tapri central was cheaper, 600 per person",
    ]
    assert median_price_inr(snippets, *FOOD_BOUNDS, min_samples=2) == 650.0


def test_foreign_currency_after_price_verb_not_misread_as_inr():
    # A number following a price-reporting verb is only assumed to be INR
    # if no other currency word is attached to it — "5000 baht" must not
    # be read as ₹5000.
    amounts = extract_price_mentions_inr(["Cost about 5000 baht for the week."], *STAY_BOUNDS)
    assert amounts == []


# --- Topic-context anchoring, added 2026-07-21 after live-verifying a real
# false positive: a Paris "stay" grounding query pulled in nightclub cover
# charges ("Rex Club, about €15") and confidently reported them as a
# nightly hotel rate. ---

def test_context_keywords_reject_off_topic_amount_for_stay():
    # A real false positive this guards against: a nightlife snippet with
    # an in-bounds € amount that has nothing to do with a hotel rate.
    snippet = "Rex Club (near the Grand Rex, house/electro, about €15). Pigalle is trashy, €20."
    amounts = extract_price_mentions_inr([snippet], *STAY_BOUNDS, context_keywords=STAY_CONTEXT_KEYWORDS)
    assert amounts == []


def test_context_keywords_accept_on_topic_stay_amount():
    snippet = "Booked a hotel room for ₹4500 a night, clean and central."
    amounts = extract_price_mentions_inr([snippet], *STAY_BOUNDS, context_keywords=STAY_CONTEXT_KEYWORDS)
    assert amounts == [4500.0]


def test_context_keywords_accept_on_topic_food_amount():
    snippet = "Thali at the local restaurant was 250 per person, filling."
    amounts = extract_price_mentions_inr([snippet], *(50, 5000), context_keywords=FOOD_CONTEXT_KEYWORDS)
    assert amounts == [250.0]


def test_context_keywords_reject_off_topic_amount_for_food():
    snippet = "The taxi from the airport cost ₹800, quick ride."
    amounts = extract_price_mentions_inr([snippet], *(50, 5000), context_keywords=FOOD_CONTEXT_KEYWORDS)
    assert amounts == []


def test_no_context_keywords_means_unfiltered_default_behavior():
    # Omitting context_keywords keeps every existing caller's behavior
    # unchanged — no filtering applied.
    snippet = "Rex Club (near the Grand Rex, house/electro, about €15)."
    amounts = extract_price_mentions_inr([snippet], *STAY_BOUNDS)
    assert amounts == [15 * 90.0]


def test_median_price_inr_applies_context_keywords():
    snippets = [
        "Rex Club, about €15 cover charge.",  # off-topic, rejected
        "Hotel room was ₹4500 a night.",
        "Guesthouse stay was ₹4800 per night, nice courtyard.",
    ]
    assert median_price_inr(snippets, *STAY_BOUNDS, min_samples=2, context_keywords=STAY_CONTEXT_KEYWORDS) == 4650.0


# --- Food per-meal -> per-day reconciliation, added 2026-07-24 (NEXT_SESSION
# _TODO "item A" proper fix): Wikivoyage "Eat" prices are per-dish/per-meal, so
# a per_day_meal_multiplier scales per-meal amounts to a day's food budget,
# leaving amounts already expressed per-day un-scaled. ---

FOOD_PP_BOUNDS = (100, 10_000)


def test_per_day_multiplier_scales_per_meal_amount():
    # A ₹300 dish, unit-less (Wikivoyage "Eat" style) -> per-day at x3 = ₹900.
    amounts = extract_price_mentions_inr(
        ["Thali at the dhaba was ₹300, filling."], *FOOD_PP_BOUNDS,
        context_keywords=FOOD_CONTEXT_KEYWORDS, per_day_meal_multiplier=3.0,
    )
    assert amounts == [900.0]


def test_per_day_multiplier_leaves_already_daily_amount_unscaled():
    # An amount explicitly per-day must NOT be multiplied again.
    amounts = extract_price_mentions_inr(
        ["We spent about ₹1500 per day on food each."], *FOOD_PP_BOUNDS,
        context_keywords=FOOD_CONTEXT_KEYWORDS, per_day_meal_multiplier=3.0,
    )
    assert amounts == [1500.0]


def test_per_day_multiplier_bounds_apply_to_reconciled_value():
    # A ₹50 street snack is below the 100 per-day floor raw, but x3 = ₹150 is
    # in-bounds and kept — the bound is on the reconciled per-day figure.
    amounts = extract_price_mentions_inr(
        ["Momos were just ₹50 a plate at the food stall."], *FOOD_PP_BOUNDS,
        context_keywords=FOOD_CONTEXT_KEYWORDS, per_day_meal_multiplier=3.0,
    )
    assert amounts == [150.0]


def test_per_day_multiplier_discards_when_reconciled_over_high_bound():
    # A ₹4000 "dish" reconciled to ₹12000/day exceeds the 10000 bound and is
    # dropped (almost certainly not actually a single meal's price).
    amounts = extract_price_mentions_inr(
        ["Some restaurant meal was ₹4000, splurge."], *FOOD_PP_BOUNDS,
        context_keywords=FOOD_CONTEXT_KEYWORDS, per_day_meal_multiplier=3.0,
    )
    assert amounts == []


def test_no_multiplier_leaves_food_amounts_raw():
    # Backward-compatible: omitting the multiplier keeps the raw per-meal value.
    amounts = extract_price_mentions_inr(
        ["Thali was ₹300."], *FOOD_PP_BOUNDS, context_keywords=FOOD_CONTEXT_KEYWORDS,
    )
    assert amounts == [300.0]


def test_median_food_per_day_mixes_meal_and_daily_correctly():
    snippets = [
        "Breakfast thali ₹200 at the cafe.",          # per-meal -> x3 = 600
        "Lunch buffet was ₹300 per person, great.",   # per-meal -> x3 = 900
        "Honestly we spent ₹900 per day on food.",     # already daily -> 900
    ]
    # Reconciled values: [600, 900, 900] -> median 900.
    assert median_price_inr(
        snippets, *FOOD_PP_BOUNDS, min_samples=2,
        context_keywords=FOOD_CONTEXT_KEYWORDS, per_day_meal_multiplier=3.0,
    ) == 900.0


# ---------------------------------------------------------------------------
# Lexical price detection (retrieval fix — see core/cost_grounding.py::
# community_price_samples for why selection is lexical rather than semantic)
# ---------------------------------------------------------------------------

def test_has_price_mention_detects_all_three_passes():
    assert has_price_mention("Room was ₹4500 a night.")           # symbol pass
    assert has_price_mention("Choki dani 700 per person, worth")  # bare-unit pass
    assert has_price_mention("we paid 1200 for the guide")        # price-verb pass


def test_has_price_mention_rejects_bare_numbers_without_price_context():
    # The same guards the extractor uses: timestamps/counts/dates aren't prices.
    assert not has_price_mention("watch at 10:30 for the temple shot")
    assert not has_price_mention("this video has 45000 views")
    assert not has_price_mention("no numbers here at all")


def test_price_focused_excerpt_keeps_a_late_price_in_view():
    """A blind text[:280] silently drops an amount sitting past the cutoff —
    the snippet then looks on-topic but contributes nothing extractable."""
    text = "background chatter " * 30 + "the thali was ₹250 per plate honestly"
    assert len(text) > 280
    excerpt = price_focused_excerpt(text, width=280)
    assert "₹250" in excerpt
    assert len(excerpt) <= 280
    # And the amount stays extractable end-to-end from the excerpt.
    assert extract_price_mentions_inr([excerpt], *FOOD_PP_BOUNDS,
                                      context_keywords=FOOD_CONTEXT_KEYWORDS) == [250.0]


def test_price_focused_excerpt_keeps_trailing_unit_phrase():
    text = "x" * 400 + " dinner cost ₹800 per person at that place"
    excerpt = price_focused_excerpt(text, width=280)
    assert "₹800 per person" in excerpt


def test_price_focused_excerpt_falls_back_to_head_truncation():
    text = "a" * 500
    assert price_focused_excerpt(text, width=280) == "a" * 280


def test_price_focused_excerpt_leaves_short_text_untouched():
    assert price_focused_excerpt("Thali ₹200.") == "Thali ₹200."


# ---------------------------------------------------------------------------
# Food per-day estimate: directly-observed daily data vs. reconciled per-meal
# ---------------------------------------------------------------------------

def test_food_per_day_prefers_directly_observed_daily_amounts():
    """When enough amounts are already per-day, no meals/day factor is applied
    and the result is flagged directly_observed — this is what lets the caller
    drop its safety floor (core/budget_estimator.py::_grounded_food_per_day)."""
    snippets = [
        "We spent ₹900 per day on food easily.",
        "Food budget was about ₹1100 a day for meals.",
        "A single thali is ₹200.",  # per-meal, must NOT be scaled into the result
    ]
    value, directly_observed = food_per_day_estimate_inr(
        snippets, *FOOD_PP_BOUNDS, min_samples=2, context_keywords=FOOD_CONTEXT_KEYWORDS,
    )
    assert directly_observed is True
    assert value == 1000.0  # median(900, 1100) — the ₹200 meal is excluded entirely


def test_food_per_day_falls_back_to_reconciled_when_daily_data_is_thin():
    snippets = [
        "Breakfast thali ₹200 at the cafe.",
        "Lunch buffet was ₹300 per person, great.",
    ]
    value, directly_observed = food_per_day_estimate_inr(
        snippets, *FOOD_PP_BOUNDS, min_samples=2,
        context_keywords=FOOD_CONTEXT_KEYWORDS, meals_per_day=3.0,
    )
    assert directly_observed is False
    assert value == 750.0  # median(200*3, 300*3)


def test_food_per_day_pools_when_only_one_daily_mention_exists():
    """One daily mention is below min_samples, so it pools with the reconciled
    per-meal amounts rather than being trusted alone."""
    snippets = [
        "We spent ₹900 per day on food.",
        "Thali was ₹200.",
        "Dinner ₹300 per person.",
    ]
    value, directly_observed = food_per_day_estimate_inr(
        snippets, *FOOD_PP_BOUNDS, min_samples=2,
        context_keywords=FOOD_CONTEXT_KEYWORDS, meals_per_day=3.0,
    )
    assert directly_observed is False
    assert value == 900.0  # median(900, 600, 900)


def test_food_per_day_returns_none_without_enough_signal():
    value, directly_observed = food_per_day_estimate_inr(
        ["The food was great but I forget what we paid."], *FOOD_PP_BOUNDS,
        min_samples=2, context_keywords=FOOD_CONTEXT_KEYWORDS,
    )
    assert (value, directly_observed) == (None, False)


def test_food_per_day_applies_bounds_to_the_reconciled_value():
    """Bounds must apply after scaling, not before — a ₹4000 'dish' becomes an
    implausible ₹12000/day and is dropped."""
    value, _ = food_per_day_estimate_inr(
        ["Some restaurant meal was ₹4000, splurge.", "Another dish ₹3800 there."],
        *FOOD_PP_BOUNDS, min_samples=1,
        context_keywords=FOOD_CONTEXT_KEYWORDS, meals_per_day=3.0,
    )
    assert value is None
