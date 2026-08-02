"""Unit tests for shared chip classification (`core/chips.py`).

Extracted from `wizard_chat_chain` so `chat_refine_chain` can share it rather
than growing a second copy. These tests pin the behaviours the original
comments call out as load-bearing, so the shared version cannot quietly lose
them — the whole point of the extraction is that there is one implementation to
get right.

Failure mode throughout: misclassification produces a *wrong UI*, never an
error. A multi-select group read as single-select means the first tap submits
and the user cannot pick a second theme.
"""
from __future__ import annotations

from core.chips import (
    GENERIC_CHIP_KEYWORDS,
    MULTI_SELECT_CHIP_KEYWORDS,
    is_multi_select_chips,
)


class TestMultiSelectDetection:
    def test_a_theme_group_is_multi_select(self):
        assert is_multi_select_chips(["Culture 🏛️", "Food 🍜", "Adventure 🏔️"]) is True

    def test_a_single_choice_group_is_not(self):
        # Pace: one tap should submit. Nothing here reads as a theme.
        assert is_multi_select_chips(["Relaxed 🧘", "Moderate 🚶", "Packed 🏃"]) is False

    def test_one_chip_is_never_multi_select(self):
        assert is_multi_select_chips(["Culture 🏛️"]) is False

    def test_no_chips_is_not_multi_select(self):
        assert is_multi_select_chips([]) is False

    def test_a_mixed_group_is_not_multi_select(self):
        # Every non-generic chip has to look like a theme; one outlier means
        # this is not a theme picker.
        assert is_multi_select_chips(["Culture 🏛️", "Relaxed 🧘"]) is False


class TestGenericChipCarveOut:
    def test_a_generic_chip_does_not_break_a_theme_group(self):
        # 🔴 The original bug: the themes prompt ALWAYS appends one of these,
        # so without the carve-out multi-select was never detected at all.
        assert is_multi_select_chips(["Culture 🏛️", "Food 🍜", "No preference"]) is True

    def test_every_generic_variant_is_carved_out(self):
        for generic in GENERIC_CHIP_KEYWORDS:
            assert is_multi_select_chips(["Culture 🏛️", "Food 🍜", generic]) is True, generic

    def test_generic_chips_alone_are_not_a_theme_group(self):
        # Nothing left after the carve-out means there is nothing to multi-select.
        assert is_multi_select_chips(["No preference", "Skip"]) is False


class TestWordBoundaryMatching:
    def test_place_names_containing_a_generic_keyword_are_not_carved_out(self):
        # 🔴 "any" is inside "Germany"/"Tuscany"/"Albany". Substring matching
        # classed these as generic "no preference" chips and dropped them —
        # the same character-rule family as the Devanagari `\w` bug in v10.45.
        # Dropped from the theme list, they cannot fail the theme test, so a
        # destination group would masquerade as multi-select.
        for place in ["Germany", "Tuscany", "Albany"]:
            assert is_multi_select_chips([place, "Culture 🏛️"]) is False, place

    def test_theme_keywords_match_regardless_of_decoration(self):
        # Chips arrive with emoji and capitalisation from the LLM.
        assert is_multi_select_chips(["CULTURE 🏛️", "food 🍜"]) is True


class TestSharedContract:
    def test_the_wizard_still_uses_the_shared_implementation(self):
        # The extraction re-exported the private names so existing call sites
        # kept working. If someone re-introduces a local copy, this fails —
        # which is the drift the extraction exists to prevent (v10.46's
        # normalise_choice_fields had to be applied at two independent points,
        # and fixing one would have fixed nothing).
        from chains import wizard_chat_chain

        assert wizard_chat_chain._is_multi_select_chips is is_multi_select_chips
        assert wizard_chat_chain._GENERIC_CHIP_KEYWORDS is GENERIC_CHIP_KEYWORDS
        assert wizard_chat_chain._MULTI_SELECT_CHIP_KEYWORDS is MULTI_SELECT_CHIP_KEYWORDS
