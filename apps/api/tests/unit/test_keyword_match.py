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


# --- Devanagari: `\b` silently failed on matra-final words (2026-07-27) -----
#
# Python's `\b` is defined via `\w`, and Devanagari combining vowel signs are
# not word characters, so `\bखाना\b` never matched while `\bहोटल\b` did —
# purely because one word ends in a matra and the other in a consonant. On the
# Hindi YouTube narration corpus this meant 0 of 24 price-bearing chunks
# matched any food or stay keyword.

def test_matches_devanagari_word_ending_in_a_matra():
    """The regression case: `\\b` cannot match these at all."""
    assert has_keyword("हमने खाना खाया थाली ₹150 की थी", {"खाना"}) is True
    assert has_keyword("हमने खाना खाया थाली ₹150 की थी", {"थाली"}) is True
    assert has_keyword("ऑटो रिक्शा से गए", {"रिक्शा"}) is True


def test_matches_devanagari_word_ending_in_a_consonant():
    """These worked before the fix and must keep working."""
    assert has_keyword("होटल का रूम ₹2000 पर नाइट", {"होटल"}) is True
    assert has_keyword("होटल का रूम ₹2000 पर नाइट", {"रूम"}) is True


def test_devanagari_keyword_does_not_match_inside_a_longer_word():
    """Boundary semantics must still hold within the script, not just across it."""
    assert has_keyword("खानापूर्ति", {"खाना"}) is False


def test_ascii_boundary_semantics_are_unchanged_by_the_devanagari_fix():
    """The lookaround pair must stay equivalent to `\\b` for ASCII."""
    assert has_keyword("great views", {"eat"}) is False
    assert has_keyword("Barbican Centre", {"bar"}) is False
    assert has_keyword("Sukhothai", {"uk"}) is False
    # `_` is a word character, so a section id like `go_next` must NOT match a
    # bare `go` — scrapers/wikivoyage.py relies on this (documented caveat).
    assert has_keyword("go_next", {"go"}) is False


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


# --- chains/wizard_chat_chain.py: "any" was matching "Germany" -------------

def test_destination_chips_are_not_treated_as_generic():
    """'Germany'/'Tuscany'/'Albany' contain 'any', so they were being classed
    as generic 'no preference' chips and dropped from the theme-chip check."""
    from chains.wizard_chat_chain import _GENERIC_CHIP_KEYWORDS

    for chip in ("Germany", "Tuscany", "Albany", "Brittany"):
        assert has_keyword(chip, _GENERIC_CHIP_KEYWORDS) is False, chip
    for chip in ("No preference", "Not sure", "Skip"):
        assert has_keyword(chip, _GENERIC_CHIP_KEYWORDS) is True, chip


# --- services/poi_pinning.py: short interest words matched inside words ----

def test_interest_keyword_does_not_match_inside_a_longer_word():
    """_interest_keywords yields any word over two chars, so 'art' matched
    'apartment' and 'zen' matched 'frozen', falsely confirming a wiki pin."""
    assert has_keyword("the apartment was frozen solid", {"art", "zen"}) is False
    assert has_keyword("the art museum and zen garden", {"art", "zen"}) is True
