"""Tests for core/scheduler.py's India events refresh job (India Workation
& Long Weekend Finder plan — `_refresh_india_events`).

Mirrors the deploy-safe cadence + exponential-backoff retry contract already
covered for `_refresh_itinerary_corpus`/`_refresh_visa_info`: the outer
`is_due()`/`mark_ran()` gate (core/job_run_state.py) survives process
restarts, and `with_backoff()` (core/retry.py) gives a transient pipeline
failure a few same-night retries before giving up — on exhaustion,
`mark_ran()` must NOT be called so tomorrow's off-peak run retries the
whole thing rather than waiting out the full 7-day cadence again.

Fully offline: `ingest_india_events`/`embed_and_store_india_events` (the
scraper's real implementation) and `is_due`/`mark_ran` are all mocked — no
real network or Qdrant calls.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import core.scheduler as scheduler


@pytest.fixture(autouse=True)
def _no_delay():
    # with_backoff() sleeps between retries; patch it out so exhaustion
    # tests run instantly rather than waiting real minutes.
    with patch("core.scheduler.asyncio.sleep", new=AsyncMock()):
        yield


class TestRefreshIndiaEvents:
    @pytest.mark.asyncio
    async def test_skips_when_not_due(self):
        with patch("core.scheduler.is_due", new=AsyncMock(return_value=False)) as mock_is_due, \
             patch("core.scheduler.mark_ran", new=AsyncMock()) as mock_mark_ran, \
             patch("scrapers.india_events.ingest_india_events", new=AsyncMock()) as mock_ingest, \
             patch("scrapers.india_events.embed_and_store_india_events", new=MagicMock()) as mock_embed:
            await scheduler._refresh_india_events()

        mock_is_due.assert_awaited_once_with(
            "india_events_refresh", interval=scheduler.timedelta(days=scheduler.settings.india_events_refresh_days)
        )
        mock_ingest.assert_not_awaited()
        mock_embed.assert_not_called()
        mock_mark_ran.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_runs_ingest_and_embed_then_marks_ran_when_due(self):
        fake_events = ["event-1", "event-2"]
        with patch("core.scheduler.is_due", new=AsyncMock(return_value=True)), \
             patch("core.scheduler.mark_ran", new=AsyncMock()) as mock_mark_ran, \
             patch("scrapers.india_events.ingest_india_events",
                   new=AsyncMock(return_value=fake_events)) as mock_ingest, \
             patch("scrapers.india_events.embed_and_store_india_events",
                   new=MagicMock(return_value=2)) as mock_embed:
            await scheduler._refresh_india_events()

        mock_ingest.assert_awaited_once_with()
        mock_embed.assert_called_once_with(fake_events)
        mock_mark_ran.assert_awaited_once_with("india_events_refresh")

    @pytest.mark.asyncio
    async def test_does_not_mark_ran_when_retries_are_exhausted(self):
        with patch("core.scheduler.is_due", new=AsyncMock(return_value=True)), \
             patch("core.scheduler.mark_ran", new=AsyncMock()) as mock_mark_ran, \
             patch("scrapers.india_events.ingest_india_events",
                   new=AsyncMock(side_effect=RuntimeError("source outage"))) as mock_ingest, \
             patch("scrapers.india_events.embed_and_store_india_events",
                   new=MagicMock()) as mock_embed:
            # Should not raise — the job swallows the exhausted-retry error
            # and simply leaves is_due() true for tomorrow's run.
            await scheduler._refresh_india_events()

        assert mock_ingest.await_count == 4  # max_attempts used by the job
        mock_embed.assert_not_called()
        mock_mark_ran.assert_not_awaited()
