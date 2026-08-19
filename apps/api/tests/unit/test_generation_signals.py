"""Unit tests for services/generation_signals.py — the pure quality-score
formula and quiet-period readiness check (issue #34), fully offline.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from services.generation_signals import (
    QUIET_PERIOD,
    _compute_quality_score,
    _signal_ready_to_score,
)


class TestComputeQualityScore:
    def test_baseline_with_no_signals(self):
        assert _compute_quality_score({}) == 1.0  # not regenerated (missing == falsy) => +0.30 => 1.0 clamp

    def test_not_regenerated_and_long_session(self):
        score = _compute_quality_score({
            "regenerated_count": 0,
            "session_duration_s": 300,
            "was_shared": False,
            "post_gen_chat_turns": 0,
        })
        assert score == 1.0  # 0.70 + 0.30 + 0.25 clamps to 1.0

    def test_all_positive_signals_clamp_at_one(self):
        score = _compute_quality_score({
            "regenerated_count": 0,
            "session_duration_s": 300,
            "was_shared": True,
            "post_gen_chat_turns": 3,
        })
        assert score == 1.0

    def test_regenerated_once_penalises(self):
        score = _compute_quality_score({
            "regenerated_count": 1,
            "session_duration_s": None,
            "was_shared": False,
            "post_gen_chat_turns": 0,
        })
        # baseline 0.70, no "+0.30 not regenerated", -0.20 regen penalty
        assert score == 0.50

    def test_regenerated_twice_plus_caps_penalty_at_040(self):
        score = _compute_quality_score({
            "regenerated_count": 3,
            "session_duration_s": None,
            "was_shared": False,
            "post_gen_chat_turns": 0,
        })
        # baseline 0.70 - 0.40 (capped) = 0.30
        assert score == 0.30

    def test_bounced_short_session_penalised(self):
        score = _compute_quality_score({
            "regenerated_count": 0,
            "session_duration_s": 10,
            "was_shared": False,
            "post_gen_chat_turns": 0,
        })
        # 0.70 + 0.30 (not regenerated) - 0.15 (bounced) = 0.85
        assert score == 0.85

    def test_score_never_below_zero(self):
        score = _compute_quality_score({
            "regenerated_count": 10,
            "session_duration_s": 5,
            "was_shared": False,
            "post_gen_chat_turns": 0,
        })
        assert score >= 0.0


class TestSignalReadyToScore:
    def _row(self, session_duration_s=None, last_updated_at=None):
        row = MagicMock()
        row.session_duration_s = session_duration_s
        row.last_updated_at = last_updated_at or datetime.now(UTC)
        return row

    def test_ready_when_session_duration_reported(self):
        row = self._row(session_duration_s=42)
        assert _signal_ready_to_score(row) is True

    def test_not_ready_when_recently_updated_and_no_duration(self):
        row = self._row(last_updated_at=datetime.now(UTC))
        assert _signal_ready_to_score(row) is False

    def test_ready_after_quiet_period_elapses(self):
        stale = datetime.now(UTC) - QUIET_PERIOD - timedelta(minutes=1)
        row = self._row(last_updated_at=stale)
        assert _signal_ready_to_score(row) is True

    def test_handles_naive_datetime_as_utc(self):
        # SQLite doesn't round-trip tz-aware datetimes — same caveat noted
        # in services/user_last_itinerary.py::_as_utc.
        stale_naive = datetime.now(UTC).replace(tzinfo=None) - QUIET_PERIOD - timedelta(minutes=1)
        row = self._row(last_updated_at=stale_naive)
        assert _signal_ready_to_score(row) is True
