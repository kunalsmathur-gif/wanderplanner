"""
Unit tests for core/job_run_state.py — deploy-safe scheduler cadence gating
(see db_models/job_run_state.py for the root cause this addresses: the
default in-memory APScheduler job store resets a job's IntervalTrigger
clock on every process restart). Fully offline against an in-memory SQLite
engine, same pattern as tests/unit/test_destination_ingestion.py.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import core.job_run_state as jrs
from db import Base


@pytest_asyncio.fixture
async def session_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    with patch.object(jrs, "AsyncSessionLocal", maker):
        yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_is_due_true_when_never_run(session_maker):
    assert await jrs.is_due("never_run_job", interval=timedelta(days=7)) is True


@pytest.mark.asyncio
async def test_is_due_false_immediately_after_mark_ran(session_maker):
    job_id = "fresh_job"
    await jrs.mark_ran(job_id)
    assert await jrs.is_due(job_id, interval=timedelta(days=7)) is False


@pytest.mark.asyncio
async def test_is_due_true_once_interval_elapsed(session_maker):
    job_id = "stale_job"
    eight_days_ago = datetime.now(UTC) - timedelta(days=8)
    await jrs.mark_ran(job_id, when=eight_days_ago)
    assert await jrs.is_due(job_id, interval=timedelta(days=7)) is True


@pytest.mark.asyncio
async def test_is_due_false_just_under_interval(session_maker):
    job_id = "almost_due_job"
    six_days_ago = datetime.now(UTC) - timedelta(days=6)
    await jrs.mark_ran(job_id, when=six_days_ago)
    assert await jrs.is_due(job_id, interval=timedelta(days=7)) is False


@pytest.mark.asyncio
async def test_mark_ran_is_idempotent_upsert(session_maker):
    """Calling mark_ran twice must update the same row, not create a second
    one — job_id is the primary key, so a naive INSERT-only implementation
    would crash on the second call."""
    job_id = "repeated_job"
    first_run = datetime.now(UTC) - timedelta(days=10)
    await jrs.mark_ran(job_id, when=first_run)
    second_run = datetime.now(UTC)
    await jrs.mark_ran(job_id, when=second_run)

    recorded = await jrs.last_run_at(job_id)
    assert recorded is not None
    assert abs((recorded - second_run).total_seconds()) < 1


@pytest.mark.asyncio
async def test_restart_does_not_reset_cadence(session_maker):
    """Core regression test for the bug being fixed: simulate a job that ran
    once, long before the configured interval, then simulate N process
    'restarts' (which in the old design would each reset an in-memory
    IntervalTrigger's next-fire clock to restart_time + interval). With
    DB-persisted state, is_due() must depend only on the last real run, not
    on how many times the check function itself is invoked/process restarts
    occur in between.
    """
    job_id = "restart_resilient_job"
    interval = timedelta(days=7)
    last_real_run = datetime.now(UTC) - timedelta(days=7, hours=1)  # just past due
    await jrs.mark_ran(job_id, when=last_real_run)

    # Simulate many restart-triggered "check" calls in quick succession —
    # none of these should themselves count as a run or push the due-ness
    # further away; is_due should consistently report True until mark_ran
    # is actually called again.
    for _ in range(5):
        assert await jrs.is_due(job_id, interval=interval) is True

    # Now the job actually runs and marks completion.
    await jrs.mark_ran(job_id)

    # Immediately after, even many more simulated restarts must NOT show it
    # as due again — this is exactly the scenario that broke before: a
    # deploy right after a real run must not force another full wait.
    for _ in range(5):
        assert await jrs.is_due(job_id, interval=interval) is False
