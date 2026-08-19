"""Tests for core/scheduler.py's quality-score background job (issue #34).

Mirrors tests/unit/test_scheduler_youtube_refresh.py's pattern: an in-memory
sqlite engine patched onto `db.AsyncSessionLocal` (the module the job imports
from at call time), Qdrant fully mocked — fully offline.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import core.scheduler as scheduler
import db as db_module
from db import Base
from db_models import GeneratedItinerarySignal


@pytest_asyncio.fixture
async def session_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    with patch.object(db_module, "AsyncSessionLocal", maker):
        yield maker
    await engine.dispose()


class TestScoreGeneratedItineraryQualityJob:
    @pytest.mark.asyncio
    async def test_scores_ready_rows_and_logs_count(self, session_maker):
        async with session_maker() as db:
            db.add(GeneratedItinerarySignal(
                generation_id="900",
                regenerated_count=0,
                session_duration_s=200,
                was_shared=False,
                post_gen_chat_turns=0,
            ))
            await db.commit()

        mock_client = MagicMock()
        with patch("core.qdrant.get_qdrant", return_value=mock_client):
            await scheduler._score_generated_itinerary_quality()

        mock_client.set_payload.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_is_swallowed(self, session_maker):
        with patch(
            "services.generation_signals.score_ready_generation_signals",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise.
            await scheduler._score_generated_itinerary_quality()
