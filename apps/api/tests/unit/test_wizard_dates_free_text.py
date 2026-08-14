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

from chains.wizard_chat_chain import _infer_dates_from_free_text

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
