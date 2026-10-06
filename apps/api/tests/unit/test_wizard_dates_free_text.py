"""Regression tests for _infer_dates_from_free_text (chains/wizard_chat_chain.py).

Gap found (2026-08-13): unlike purpose/pace/budget/group, `dates` had NO
free-text fallback at all. If Gemini's JSON was malformed on the turn the
user states their travel window (e.g. "November 13th to 19th"), the answer
was silently lost -- the except-branch fell back to the pre-patch
`request.partial_config`, and the question would be re-asked with no record
the user had already answered it.
"""
from __future__ import annotations

from datetime import date

from chains.wizard_chat_chain import (
    _infer_dates_from_free_text,
    _infer_vague_duration_dates_from_free_text,
    _infer_weekend_dates_from_free_text,
)

REF = date(2026, 8, 12)


def test_month_first_ordinal_range():
    assert _infer_dates_from_free_text("November 13th to 19th", reference_date=REF) == {
        "start": "2026-11-13",
        "end": "2026-11-19",
        "flexible": False,
    }


def test_day_first_ordinal_range():
    assert _infer_dates_from_free_text("13th to 19th November", reference_date=REF) == {
        "start": "2026-11-13",
        "end": "2026-11-19",
        "flexible": False,
    }


def test_abbreviated_month_with_hyphen_range():
    assert _infer_dates_from_free_text("Nov 13-19", reference_date=REF) == {
        "start": "2026-11-13",
        "end": "2026-11-19",
        "flexible": False,
    }


def test_explicit_year_is_respected():
    assert _infer_dates_from_free_text("December 20 to 27, 2026", reference_date=REF) == {
        "start": "2026-12-20",
        "end": "2026-12-27",
        "flexible": False,
    }


def test_rolls_forward_to_next_year_when_month_already_passed():
    """Reference date is August 2026; a January range with no year must
    resolve to the *next* January (2027), not the one already gone by."""
    assert _infer_dates_from_free_text("5th to 10th Jan", reference_date=REF) == {
        "start": "2027-01-05",
        "end": "2027-01-10",
        "flexible": False,
    }


def test_cross_month_ranges_are_not_handled():
    """A range spanning a month boundary ("25th to the 3rd November") is
    deliberately out of scope -- returns None rather than guessing wrong."""
    assert _infer_dates_from_free_text("the 25th to the 3rd November", reference_date=REF) is None


def test_returns_none_without_a_month_name():
    """Bare numeric ranges are locale-ambiguous (day/month order) and must
    not be guessed at."""
    assert _infer_dates_from_free_text("13 to 19", reference_date=REF) is None
    assert _infer_dates_from_free_text(None, reference_date=REF) is None


class TestInferWeekendDatesFromFreeText:
    """Regression tests for _infer_weekend_dates_from_free_text.

    Bug fix (live-reported): "plan a trip for any weekend" had no explicit
    handling anywhere, and the LLM improvised a date range spanning every
    remaining weekend of the year (~62 days) instead of resolving to a
    single weekend -- which then tripped the max-trip-length guard with a
    scope the user never asked for.
    """

    def test_any_weekend_resolves_to_upcoming_saturday_sunday(self):
        # REF = Wed 2026-08-12 -> next Saturday is 2026-08-15.
        assert _infer_weekend_dates_from_free_text("plan a trip for any weekend", reference_date=REF) == {
            "start": "2026-08-15",
            "end": "2026-08-16",
            "flexible": False,
            "duration_days": 2,
        }

    def test_a_weekend_and_some_weekend_and_this_weekend_all_match(self):
        for phrase in ["a weekend getaway", "some weekend soon", "this weekend", "next weekend"]:
            result = _infer_weekend_dates_from_free_text(phrase, reference_date=REF)
            assert result == {
                "start": "2026-08-15",
                "end": "2026-08-16",
                "flexible": False,
                "duration_days": 2,
            }

    def test_rolls_to_next_week_when_reference_date_is_itself_saturday(self):
        # 2026-08-15 is itself a Saturday -- "any weekend" said that day
        # should mean the UPCOMING one, not "right now, already half over".
        saturday = date(2026, 8, 15)
        assert _infer_weekend_dates_from_free_text("any weekend works", reference_date=saturday) == {
            "start": "2026-08-22",
            "end": "2026-08-23",
            "flexible": False,
            "duration_days": 2,
        }

    def test_named_weekend_with_specific_date_is_not_handled(self):
        """A weekend tied to a specific named date/period is left to the
        LLM -- this parser only resolves the vague, unanchored phrasing."""
        assert _infer_weekend_dates_from_free_text("the last weekend of November", reference_date=REF) is None

    def test_returns_none_without_weekend_mention(self):
        assert _infer_weekend_dates_from_free_text("5 days in Goa", reference_date=REF) is None
        assert _infer_weekend_dates_from_free_text(None, reference_date=REF) is None


class TestInferVagueDurationDatesFromFreeText:
    """Regression tests for _infer_vague_duration_dates_from_free_text.

    Generalises the "any weekend" fix (user feedback): "plan a trip for a
    week" / "a month" (no month/season named) had the same anchor-free gap
    -- the user is undecided on exact dates, not asking the assistant to
    stall on a clarifying question or guess an enormous window. Resolve to
    ONE concrete, near-term window instead.
    """

    def test_a_week_resolves_to_next_monday_through_sunday(self):
        # REF = Wed 2026-08-12 -> next Monday is 2026-08-17, +6 days = 08-23.
        assert _infer_vague_duration_dates_from_free_text("plan a trip for a week", reference_date=REF) == {
            "start": "2026-08-17",
            "end": "2026-08-23",
            "flexible": False,
            "duration_days": 7,
        }

    def test_one_week_phrasing_also_matches(self):
        assert _infer_vague_duration_dates_from_free_text("I want one week off", reference_date=REF) == {
            "start": "2026-08-17",
            "end": "2026-08-23",
            "flexible": False,
            "duration_days": 7,
        }

    def test_rolls_to_next_week_when_reference_date_is_itself_monday(self):
        monday = date(2026, 8, 17)
        assert _infer_vague_duration_dates_from_free_text("a week trip", reference_date=monday) == {
            "start": "2026-08-24",
            "end": "2026-08-30",
            "flexible": False,
            "duration_days": 7,
        }

    def test_a_month_resolves_to_a_flexible_30_day_window_starting_today(self):
        assert _infer_vague_duration_dates_from_free_text("planning for a month", reference_date=REF) == {
            "start": "2026-08-12",
            "end": "2026-09-10",
            "flexible": True,
            "duration_days": 30,
        }

    def test_one_month_phrasing_also_matches(self):
        assert _infer_vague_duration_dates_from_free_text("one month trip", reference_date=REF) == {
            "start": "2026-08-12",
            "end": "2026-09-10",
            "flexible": True,
            "duration_days": 30,
        }

    def test_named_month_is_not_treated_as_vague_duration(self):
        """"A week in November" already names a period -- that's the
        model's existing month+duration handling, not this parser's job."""
        assert _infer_vague_duration_dates_from_free_text("a week in November", reference_date=REF) is None
        assert _infer_vague_duration_dates_from_free_text("a month long trip in December", reference_date=REF) is None

    def test_returns_none_without_a_vague_duration_phrase(self):
        assert _infer_vague_duration_dates_from_free_text("5 days in Goa", reference_date=REF) is None
        assert _infer_vague_duration_dates_from_free_text(None, reference_date=REF) is None
