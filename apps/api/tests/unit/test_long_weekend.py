"""Unit tests for services/long_weekend.py — India long-weekend finder.

Pure date math, so every test pins a fixed ``year`` (and, where relevant, a
fixed state) rather than depending on ``date.today()`` — see
``get_long_weekends``'s ``year`` parameter, which is exactly how this module
exposes a deterministic "today" override for testability without needing
freezegun (not currently a dependency of this repo).
"""
from __future__ import annotations

from datetime import date

import pytest

from services.long_weekend import (
    LongWeekendWindow,
    drop_elapsed_windows,
    get_holidays_for_state,
    get_long_weekends,
)


class TestGetHolidaysForState:
    def test_known_state_includes_national_and_state_holidays(self):
        holidays = get_holidays_for_state("Karnataka", 2026)
        names = {h.name for h in holidays}
        assert any("Republic Day" in n for n in names)
        assert any("Rajyotsava" in n for n in names)

    def test_filters_to_requested_year_only(self):
        holidays = get_holidays_for_state("Karnataka", 2026)
        assert all(h.date.year == 2026 for h in holidays)

    def test_unknown_state_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown state"):
            get_holidays_for_state("Atlantis", 2026)


class TestGetLongWeekends:
    def test_holiday_adjacent_to_weekend_needs_no_leave(self):
        # Republic Day 2026-01-26 falls on a Monday -> Sat 24 / Sun 25 / Mon
        # 26 is a 3-day window with zero leave days needed.
        windows = get_long_weekends("Karnataka", 2026)
        republic_day_window = next(
            w for w in windows if w.start_date == date(2026, 1, 24)
        )
        assert republic_day_window.end_date == date(2026, 1, 26)
        assert republic_day_window.total_days_off == 3
        assert republic_day_window.leave_days_needed == 0
        assert "Republic Day" in republic_day_window.reason
        assert "weekend" in republic_day_window.reason

    def test_bridge_day_connects_holiday_to_weekend(self):
        # Karnataka Rajyotsava / Guru Nanak Jayanti 2026-11-24 is a Tuesday,
        # immediately following the Sat 21 / Sun 22 weekend with Mon 23 as a
        # single bridge (leave) day -> 4 days off for 1 leave day.
        windows = get_long_weekends("Karnataka", 2026)
        bridge_window = next(
            w for w in windows if w.start_date == date(2026, 11, 21) and w.leave_days_needed == 1
        )
        assert bridge_window.end_date == date(2026, 11, 24)
        assert bridge_window.total_days_off == 4
        assert bridge_window.leave_days_needed == 1
        assert bridge_window.value == pytest.approx(4.0)

    def test_windows_ranked_best_value_first(self):
        windows = get_long_weekends("Karnataka", 2026)
        assert len(windows) > 1
        values = [w.value for w in windows]
        assert values == sorted(values, reverse=True)
        # The top-ranked window should have the highest days-off-per-leave-day.
        assert windows[0].value >= windows[-1].value

    def test_plain_weekend_with_no_holiday_is_excluded(self):
        # A reason of exactly "weekend" (no holiday name) would mean an
        # ordinary Sat/Sun with nothing special about it leaked into the
        # results — every window must be anchored to at least one holiday.
        windows = get_long_weekends("Karnataka", 2026)
        assert all(w.reason != "weekend" for w in windows)

    def test_defaults_year_to_current_year_when_omitted(self):
        this_year_windows = get_long_weekends("Karnataka", date.today().year)
        default_windows = get_long_weekends("Karnataka")
        assert [w.start_date for w in this_year_windows] == [w.start_date for w in default_windows]

    def test_invalid_state_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown state"):
            get_long_weekends("Narnia", 2026)

    def test_all_windows_are_long_weekend_window_instances(self):
        windows = get_long_weekends("Tamil Nadu", 2026)
        assert all(isinstance(w, LongWeekendWindow) for w in windows)


class TestDropElapsedWindows:
    def test_drops_windows_that_have_already_fully_ended(self):
        windows = get_long_weekends("Karnataka", 2026)
        today = date(2026, 10, 6)
        filtered = drop_elapsed_windows(windows, today=today)
        assert all(w.end_date >= today for w in filtered)
        assert len(filtered) < len(windows)  # some 2026 windows precede October

    def test_keeps_a_window_already_in_progress(self):
        windows = get_long_weekends("Karnataka", 2026)
        in_progress = next(w for w in windows if w.start_date == date(2026, 1, 24))
        today = date(2026, 1, 25)  # inside the Jan 24-26 window
        filtered = drop_elapsed_windows(windows, today=today)
        assert in_progress in filtered

    def test_defaults_to_date_today_when_unset(self):
        windows = get_long_weekends("Karnataka", 2026)
        filtered = drop_elapsed_windows(windows)
        assert all(w.end_date >= date.today() for w in filtered)
