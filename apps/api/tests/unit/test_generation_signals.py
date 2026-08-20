"""Unit tests for services/generation_signals.py — the pure quality-score
formula and quiet-period readiness check (issue #34), fully offline.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import services.generation_signals as generation_signals
from db_models import GeneratedItinerarySignal
from services.generation_signals import (
    QUIET_PERIOD,
    _compute_quality_score,
    _signal_ready_to_score,
    record_share_signal,
    score_ready_generation_signals,
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


@pytest.mark.asyncio
class TestRecordShareSignal:
    async def test_sets_was_shared_via_own_session(self, db_session_maker):
        from sqlalchemy import select

        from db_models import GeneratedItinerarySignal

        with patch.object(generation_signals, "AsyncSessionLocal", db_session_maker):
            await record_share_signal("55")

        async with db_session_maker() as session:
            row = (
                await session.execute(
                    select(GeneratedItinerarySignal).where(GeneratedItinerarySignal.generation_id == "55")
                )
            ).scalar_one()
            assert row.was_shared is True

    async def test_failure_is_swallowed(self):
        def _boom():
            raise RuntimeError("boom")

        with patch.object(generation_signals, "AsyncSessionLocal", _boom):
            # Must not raise.
            await record_share_signal("66")


@pytest.mark.asyncio
class TestScoreReadyGenerationSignals:
    async def _add(self, db_session_maker, **kwargs):
        async with db_session_maker() as session:
            row = GeneratedItinerarySignal(**kwargs)
            session.add(row)
            await session.commit()

    async def test_scores_row_ready_via_explicit_duration(self, db_session_maker):
        from sqlalchemy import select

        await self._add(
            db_session_maker,
            generation_id="100",
            regenerated_count=0,
            session_duration_s=200,
            was_shared=False,
            post_gen_chat_turns=0,
        )
        mock_client = MagicMock()
        with patch("core.qdrant.get_qdrant", return_value=mock_client):
            async with db_session_maker() as session:
                scored = await score_ready_generation_signals(session, batch_size=200)

        assert scored == 1
        mock_client.set_payload.assert_called_once()
        _, call_kwargs = mock_client.set_payload.call_args
        assert call_kwargs["points"] == [100]
        assert call_kwargs["payload"]["quality_score"] == pytest.approx(min(0.70 + 0.30 + 0.25, 1.0))

        async with db_session_maker() as session:
            row = (
                await session.execute(
                    select(GeneratedItinerarySignal).where(GeneratedItinerarySignal.generation_id == "100")
                )
            ).scalar_one()
            assert row.scored_at is not None

    async def test_scores_row_ready_via_quiet_period(self, db_session_maker):
        stale = datetime.now(UTC) - QUIET_PERIOD - timedelta(minutes=1)
        await self._add(
            db_session_maker,
            generation_id="101",
            regenerated_count=1,
            session_duration_s=None,
            was_shared=True,
            post_gen_chat_turns=2,
            last_updated_at=stale,
        )
        mock_client = MagicMock()
        with patch("core.qdrant.get_qdrant", return_value=mock_client):
            async with db_session_maker() as session:
                scored = await score_ready_generation_signals(session, batch_size=200)

        assert scored == 1
        mock_client.set_payload.assert_called_once()

    async def test_skips_row_not_ready(self, db_session_maker):
        await self._add(
            db_session_maker,
            generation_id="102",
            regenerated_count=0,
            session_duration_s=None,
            was_shared=False,
            post_gen_chat_turns=0,
        )
        mock_client = MagicMock()
        with patch("core.qdrant.get_qdrant", return_value=mock_client):
            async with db_session_maker() as session:
                scored = await score_ready_generation_signals(session, batch_size=200)

        assert scored == 0
        mock_client.set_payload.assert_not_called()

    async def test_skips_already_scored_row(self, db_session_maker):
        await self._add(
            db_session_maker,
            generation_id="103",
            regenerated_count=0,
            session_duration_s=200,
            was_shared=False,
            post_gen_chat_turns=0,
            scored_at=datetime.now(UTC),
        )
        mock_client = MagicMock()
        with patch("core.qdrant.get_qdrant", return_value=mock_client):
            async with db_session_maker() as session:
                scored = await score_ready_generation_signals(session, batch_size=200)

        assert scored == 0
        mock_client.set_payload.assert_not_called()

    async def test_respects_batch_size_cap(self, db_session_maker):
        for i in range(5):
            await self._add(
                db_session_maker,
                generation_id=str(200 + i),
                regenerated_count=0,
                session_duration_s=200,
                was_shared=False,
                post_gen_chat_turns=0,
            )
        mock_client = MagicMock()
        with patch("core.qdrant.get_qdrant", return_value=mock_client):
            async with db_session_maker() as session:
                scored = await score_ready_generation_signals(session, batch_size=2)

        assert scored == 2
        assert mock_client.set_payload.call_count == 2

    async def test_per_row_failure_does_not_abort_batch(self, db_session_maker):
        await self._add(
            db_session_maker,
            generation_id="not-an-int",
            regenerated_count=0,
            session_duration_s=200,
            was_shared=False,
            post_gen_chat_turns=0,
        )
        await self._add(
            db_session_maker,
            generation_id="300",
            regenerated_count=0,
            session_duration_s=200,
            was_shared=False,
            post_gen_chat_turns=0,
        )
        mock_client = MagicMock()
        with patch("core.qdrant.get_qdrant", return_value=mock_client):
            async with db_session_maker() as session:
                scored = await score_ready_generation_signals(session, batch_size=200)

        # "not-an-int" can't be cast to int for the Qdrant point id, so it's
        # skipped; the well-formed row after it is still scored.
        assert scored == 1
