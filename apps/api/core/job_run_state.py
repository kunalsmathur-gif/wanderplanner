"""Deploy-safe scheduler cadence gating (see db_models/job_run_state.py for
the root cause this addresses: APScheduler's default in-memory job store
resets a job's `IntervalTrigger` clock on every process restart, so a job
with no persisted state of its own would silently drift or starve under
frequent deploys).

Jobs that already have their own domain-level staleness tracking (e.g.
`_refresh_osm_pois`/`_refresh_youtube_comments`, gated per-destination via
`DestinationIngestionState`) don't need this — it's for jobs whose cadence
isn't naturally tied to some other table.

Usage: register the APScheduler trigger on a short, cheap "check" cadence
(e.g. hourly) and call `is_due()` at the top of the job body to decide
whether to actually do the expensive work; call `mark_ran()` after a
successful run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from db import AsyncSessionLocal
from db_models import JobRunState


async def is_due(job_id: str, *, interval: timedelta) -> bool:
    """True if `job_id` has never run, or its last recorded run is older
    than `interval` — independent of how long the current process has been
    up."""
    async with AsyncSessionLocal() as db:
        row = await db.get(JobRunState, job_id)
        if row is None:
            return True
        return datetime.now(UTC) - _as_aware_utc(row.last_run_at) >= interval


async def mark_ran(job_id: str, *, when: datetime | None = None) -> None:
    """Record a successful completion. Call only after the real work
    succeeds — a failed run should be retried on the next check tick, not
    treated as done."""
    when = when or datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        row = await db.get(JobRunState, job_id)
        if row is None:
            db.add(JobRunState(job_id=job_id, last_run_at=when))
        else:
            row.last_run_at = when
        await db.commit()


async def last_run_at(job_id: str) -> datetime | None:
    """Read-only accessor, mainly for admin/debug surfaces."""
    async with AsyncSessionLocal() as db:
        row = await db.execute(select(JobRunState).where(JobRunState.job_id == job_id))
        state = row.scalar_one_or_none()
        return _as_aware_utc(state.last_run_at) if state else None


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite (used in local dev/tests) drops tzinfo on round-trip even for
    a `DateTime(timezone=True)` column, while Postgres (production) preserves
    it — this always writes UTC-aware datetimes, so a naive value read back
    can safely be assumed to already be UTC rather than the local clock."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
