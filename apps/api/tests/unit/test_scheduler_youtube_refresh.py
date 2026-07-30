"""Tests for core/scheduler.py's YouTube-comment refresh job.

Kept separate from the OSM/Wikivoyage refresh because the economics differ:
`search.list` spends a metered quota, so this job is demand-ranked, per-run
capped, and must not mark a destination fresh when it got nothing back.

Postgres is an in-memory sqlite engine; the scraper is mocked — fully offline.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import core.scheduler as scheduler
import db as db_module
from db import Base
from db_models import DestinationIngestionState


@pytest_asyncio.fixture
async def session_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    # The job imports AsyncSessionLocal from `db` at call time.
    with patch.object(db_module, "AsyncSessionLocal", maker):
        yield maker
    await engine.dispose()


async def _add(maker, destination, youtube_at, request_count=1):
    now = datetime.now(UTC)
    async with maker() as db:
        db.add(DestinationIngestionState(
            destination=destination,
            osm_last_ingested_at=now,
            wiki_last_ingested_at=now,
            youtube_last_ingested_at=youtube_at,
            request_count=request_count,
            last_requested_at=now,
        ))
        await db.commit()


@pytest.fixture(autouse=True)
def _no_delay():
    with patch("core.scheduler.asyncio.sleep", new=AsyncMock()):
        yield


class TestRefreshYoutubeComments:
    @pytest.mark.asyncio
    async def test_skips_entirely_without_api_key(self, session_maker):
        await _add(session_maker, "Jaipur", None)
        with patch("core.scheduler.settings.youtube_api_key", ""), \
             patch("scrapers.youtube_comments.ingest_youtube_comments", new=AsyncMock()) as mock_ingest:
            await scheduler._refresh_youtube_comments()
        mock_ingest.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_picks_up_never_ingested_and_stale_but_not_fresh(self, session_maker):
        fresh = datetime.now(UTC)
        stale = datetime.now(UTC) - timedelta(days=90)
        await _add(session_maker, "NeverIngested", None)
        await _add(session_maker, "Stale", stale)
        await _add(session_maker, "Fresh", fresh)

        with patch("core.scheduler.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.ingest_youtube_comments",
                   new=AsyncMock(return_value=10)) as mock_ingest:
            await scheduler._refresh_youtube_comments()

        refreshed = {call.args[0] for call in mock_ingest.await_args_list}
        assert refreshed == {"NeverIngested", "Stale"}

    @pytest.mark.asyncio
    async def test_never_ingested_ranks_ahead_of_merely_stale(self, session_maker):
        stale = datetime.now(UTC) - timedelta(days=90)
        await _add(session_maker, "Stale", stale, request_count=999)
        await _add(session_maker, "NeverIngested", None, request_count=1)

        with patch("core.scheduler.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.ingest_youtube_comments",
                   new=AsyncMock(return_value=10)) as mock_ingest:
            await scheduler._refresh_youtube_comments()

        order = [call.args[0] for call in mock_ingest.await_args_list]
        assert order[0] == "NeverIngested"

    @pytest.mark.asyncio
    async def test_orders_by_demand_within_the_same_tier(self, session_maker):
        """A limited quota should be spent on what users actually ask for."""
        await _add(session_maker, "Rare", None, request_count=1)
        await _add(session_maker, "Popular", None, request_count=500)

        with patch("core.scheduler.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.ingest_youtube_comments",
                   new=AsyncMock(return_value=10)) as mock_ingest:
            await scheduler._refresh_youtube_comments()

        order = [call.args[0] for call in mock_ingest.await_args_list]
        assert order == ["Popular", "Rare"]

    @pytest.mark.asyncio
    async def test_respects_per_run_batch_cap(self, session_maker):
        for i in range(5):
            await _add(session_maker, f"Dest{i}", None, request_count=i)

        with patch("core.scheduler.settings.youtube_api_key", "fake-key"), \
             patch("core.scheduler.settings.youtube_refresh_batch_size", 2), \
             patch("scrapers.youtube_comments.ingest_youtube_comments",
                   new=AsyncMock(return_value=10)) as mock_ingest:
            await scheduler._refresh_youtube_comments()

        assert mock_ingest.await_count == 2

    @pytest.mark.asyncio
    async def test_marks_timestamp_only_on_a_successful_ingest(self, session_maker):
        await _add(session_maker, "Jaipur", None)

        with patch("core.scheduler.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.ingest_youtube_comments", new=AsyncMock(return_value=30)):
            await scheduler._refresh_youtube_comments()

        async with session_maker() as db:
            row = await db.get(DestinationIngestionState, "Jaipur")
            assert row.youtube_last_ingested_at is not None

    @pytest.mark.asyncio
    async def test_zero_comments_leaves_timestamp_null_for_next_run(self, session_maker):
        """Over budget / no videos found must stay retryable rather than being
        recorded as freshly ingested but empty."""
        await _add(session_maker, "Jaipur", None)

        with patch("core.scheduler.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.ingest_youtube_comments", new=AsyncMock(return_value=0)):
            await scheduler._refresh_youtube_comments()

        async with session_maker() as db:
            row = await db.get(DestinationIngestionState, "Jaipur")
            assert row.youtube_last_ingested_at is None

    @pytest.mark.asyncio
    async def test_one_destination_failing_does_not_abort_the_run(self, session_maker):
        await _add(session_maker, "Broken", None, request_count=10)
        await _add(session_maker, "Fine", None, request_count=5)

        async def _flaky(destination):
            if destination == "Broken":
                raise RuntimeError("quota exceeded")
            return 12

        with patch("core.scheduler.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.ingest_youtube_comments", new=_flaky):
            await scheduler._refresh_youtube_comments()

        async with session_maker() as db:
            assert (await db.get(DestinationIngestionState, "Broken")).youtube_last_ingested_at is None
            assert (await db.get(DestinationIngestionState, "Fine")).youtube_last_ingested_at is not None


class TestRetryYoutubeNarrationTranscripts:
    """Tests for the slow drip-retry job (issue #46 follow-up) — retries a
    small batch of transcript-missing destinations on a short cadence rather
    than a full-corpus burst, since a burst reliably re-triggers the YouTube
    IP block that caused the gap in the first place."""

    @pytest.mark.asyncio
    async def test_nothing_missing_is_a_clean_noop(self):
        with patch("scrapers.youtube_narration.destinations_missing_transcripts",
                   new=AsyncMock(return_value=[])), \
             patch("scrapers.youtube_narration.ingest_youtube_narration", new=AsyncMock()) as mock_ingest:
            await scheduler._retry_youtube_narration_transcripts()
        mock_ingest.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_respects_the_small_batch_cap(self):
        missing = [f"Dest{i}" for i in range(10)]
        with patch("scrapers.youtube_narration.destinations_missing_transcripts",
                   new=AsyncMock(return_value=missing)), \
             patch("core.scheduler.settings.youtube_narration_transcript_retry_batch_size", 3), \
             patch("scrapers.youtube_narration.ingest_youtube_narration",
                   new=AsyncMock(return_value=10)) as mock_ingest:
            await scheduler._retry_youtube_narration_transcripts()
        assert mock_ingest.await_count == 3
        retried = [call.args[0] for call in mock_ingest.await_args_list]
        assert retried == missing[:3]

    @pytest.mark.asyncio
    async def test_one_destination_failing_does_not_abort_the_batch(self):
        async def _flaky(destination):
            if destination == "Blocked":
                raise RuntimeError("IP blocked")
            return 12

        with patch("scrapers.youtube_narration.destinations_missing_transcripts",
                   new=AsyncMock(return_value=["Blocked", "Fine"])), \
             patch("scrapers.youtube_narration.ingest_youtube_narration", new=_flaky):
            await scheduler._retry_youtube_narration_transcripts()
        # No exception propagated — reaching this line is the assertion.

    @pytest.mark.asyncio
    async def test_lister_failure_is_a_clean_noop_not_a_crash(self):
        with patch("scrapers.youtube_narration.destinations_missing_transcripts",
                   new=AsyncMock(side_effect=RuntimeError("qdrant down"))), \
             patch("scrapers.youtube_narration.ingest_youtube_narration", new=AsyncMock()) as mock_ingest:
            await scheduler._retry_youtube_narration_transcripts()
        mock_ingest.assert_not_awaited()
