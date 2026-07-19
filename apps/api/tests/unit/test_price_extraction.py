"""Tests for core/price_extraction.py — deterministic (no-LLM) INR price
extraction from free-text community snippets."""
from core.price_extraction import extract_price_mentions_inr, median_price_inr

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
