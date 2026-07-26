"""Tests for core/keyword_match.py and the three live bugs it fixes.

Each case below is a real false positive that bare `keyword in text` produced,
found on 2026-07-26. They are written as behaviour tests against the modules
that had the bug, not just against the helper, so a regression shows up where
it would actually hurt.
"""
from chains.safety import KID_EXCLUDED_TITLE_KEYWORDS, apply_kid_safety_filter
from core.budget_estimator import resolve_destination_tier
from core.keyword_match import has_keyword
from models.itinerary import ItineraryDay, ItineraryItem, ItineraryItemLocation
from models.trip import GroupComposition, KidAge, TripConfig


def test_matches_whole_words_only():
    assert has_keyword("great views over the bay", {"eat"}) is False
    assert has_keyword("where should we eat tonight", {"eat"}) is True


def test_multi_word_keywords_still_match():
    assert has_keyword("a cocktail lounge on the roof", {"cocktail lounge"}) is True


def test_empty_text_is_not_a_match():
    assert has_keyword("", {"bar"}) is False


# --- chains/safety.py: "pub" was matching "Public Garden" ------------------

def _day(*titles):
    return ItineraryDay(
        day_number=1, date="2026-11-01", theme="Day 1",
        items=[
            ItineraryItem(id=str(i), time_start="10:00", time_end="11:00",
                          title=t, description="", location=ItineraryItemLocation(lat=0.0, lon=0.0), tags=[])
            for i, t in enumerate(titles)
        ],
    )


def _kids_config():
    return TripConfig(group=GroupComposition(adults=2, kids=[KidAge(age=6)]))


def test_kid_filter_keeps_places_that_merely_contain_a_keyword():
    """'Public Garden' contains 'pub'; 'Bara Imambara' contains 'bar'. Both are
    kid-friendly landmarks that were being silently deleted."""
    days = apply_kid_safety_filter(
        [_day("Public Garden", "Bara Imambara", "Barbican Centre", "Clubhouse Cafe")],
        _kids_config(),
    )
    kept = [item.title for item in days[0].items]
    assert kept == ["Public Garden", "Bara Imambara", "Barbican Centre", "Clubhouse Cafe"]


def test_kid_filter_still_removes_the_real_thing():
    """The filter must keep working — this is a safety feature."""
    days = apply_kid_safety_filter(
        [_day("Sky Bar", "Night Club", "Casino Royale", "Family Museum")],
        _kids_config(),
    )
    assert [item.title for item in days[0].items] == ["Family Museum"]


def test_kid_keyword_set_is_unchanged():
    """Guards against 'fixing' a false positive by deleting the keyword."""
    assert {"bar", "pub", "club", "casino"} <= KID_EXCLUDED_TITLE_KEYWORDS


# --- core/budget_estimator.py: "uk" was matching "Sukhothai" ---------------

def test_tier_does_not_match_a_country_code_inside_a_city_name():
    """'Sukhothai' contains 'uk', which put a moderate destination on the
    premium tier and inflated its budget."""
    assert resolve_destination_tier("Sukhothai", "Thailand") == "moderate"


def test_tier_still_recognises_the_real_keyword():
    assert resolve_destination_tier("London", "UK") == "premium"
    assert resolve_destination_tier("Kathmandu", "Nepal") == "budget"
    assert resolve_destination_tier("Nowhereville", "Atlantis") == "moderate"
