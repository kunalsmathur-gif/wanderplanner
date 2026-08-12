"""Regression tests for _infer_group_from_free_text (chains/wizard_chat_chain.py).

Bug (2026-08-12, prod): the group-composition follow-up ("4 couples i.e 8
adults, and 4 kids (aged 8,6,3,3)") had no free-text fallback like
purpose/pace/budget do. When Gemini's JSON response for that turn was
malformed, the except-branch fell back to the pre-patch `request.partial_config`
(adults still 0), so `_is_stale_chips` never recognised `group` as filled and
the previous turn's Solo/Couple/Family/Friends chips leaked through under the
reply that had already moved on to asking about pace.
"""
from __future__ import annotations

from chains.wizard_chat_chain import (
    _FIELD_CHIP_SETS,
    _infer_group_from_free_text,
    _is_stale_chips,
)


def test_extracts_adults_and_kid_ages_from_full_sentence():
    patch = _infer_group_from_free_text("4 couples i.e 8 adults, and 4 kids (aged 8,6,3,3)")
    assert patch == {"adults": 8, "kids": [{"age": 8}, {"age": 6}, {"age": 3}, {"age": 3}]}


def test_extracts_adults_only_when_no_kids_mentioned():
    assert _infer_group_from_free_text("just me and my partner, 2 adults") == {"adults": 2}


def test_extracts_seniors_alongside_adults_and_kids():
    patch = _infer_group_from_free_text("6 adults, 3 seniors and children aged 10, 12, 14")
    assert patch == {
        "adults": 6,
        "seniors": 3,
        "kids": [{"age": 10}, {"age": 12}, {"age": 14}],
    }


def test_returns_none_without_an_explicit_adults_marker():
    """A bare number (e.g. a day count) must never be misread as a headcount."""
    assert _infer_group_from_free_text("3 days trip") is None
    assert _infer_group_from_free_text(None) is None


def test_backfilled_group_makes_stale_group_chips_detectable():
    """End-to-end: once the free-text patch is merged into config, the
    group chip set must be recognised as stale (already-answered)."""
    fallback_config = {"group": {}}
    patch = _infer_group_from_free_text("4 couples i.e 8 adults, and 4 kids (aged 8,6,3,3)")
    fallback_config["group"] = {**fallback_config["group"], **patch}

    group_chips = list(_FIELD_CHIP_SETS["group"])
    assert _is_stale_chips(group_chips, fallback_config) is True
