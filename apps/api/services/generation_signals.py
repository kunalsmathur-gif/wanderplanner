"""Implicit session-signal capture for the `generated_itineraries` learning
flywheel (issue #34).

Every signal is a best-effort upsert against a single `generated_itinerary_
signals` row keyed by `generation_id` — the same id `ItineraryResponse.
generation_id` handed the client (see services/generated_itineraries.py::
compute_generation_id). The scheduler job in core/scheduler.py reads these
rows, computes a `quality_score`, and writes it onto the corresponding
Qdrant point — see `_compute_quality_score()` below for the formula
(mirrors docs/rag-strategy.md's "Implicit Quality Signal Scoring" table).
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db import AsyncSessionLocal
from db_models import GeneratedItinerarySignal

logger = logging.getLogger(__name__)

GenerationSignalEvent = Literal["regenerated", "chat_turn", "session_duration", "shared"]

# A session with no explicit `session_duration` report (e.g. the tab was
# closed without `beforeunload` firing, or the user simply never left the
# page during this scheduler run) is still eventually scored — once no new
# signal has arrived for this long, the scheduler treats the session as over
# rather than waiting on a report that may never come.
QUIET_PERIOD = timedelta(minutes=30)


async def record_generation_signal(
    db: AsyncSession,
    generation_id: str,
    event: GenerationSignalEvent,
    value: int | None = None,
    user_id: uuid.UUID | None = None,
) -> GeneratedItinerarySignal:
    """Upsert one signal onto `generation_id`'s row (request-scoped session —
    the caller commits as part of its own request lifecycle, same as
    routers/itinerary_feedback.py)."""
    row = await db.get(GeneratedItinerarySignal, generation_id)
    if row is None:
        row = GeneratedItinerarySignal(
            generation_id=generation_id,
            user_id=user_id,
            # Explicit Python-side defaults — SQLAlchemy's server_default/
            # default only apply at flush time, but this row's fields are
            # read/incremented before the first flush below.
            regenerated_count=0,
            was_shared=False,
            post_gen_chat_turns=0,
        )
        db.add(row)
    elif user_id is not None and row.user_id is None:
        row.user_id = user_id

    if event == "regenerated":
        row.regenerated_count += 1
    elif event == "chat_turn":
        row.post_gen_chat_turns += 1
    elif event == "shared":
        row.was_shared = True
    elif event == "session_duration":
        # Reported once, at session end — the total elapsed time, not an
        # increment. `value` is required for this event (validated at the
        # API layer via GenerationSignalRequest).
        if value is not None:
            row.session_duration_s = value
    else:
        raise ValueError(f"unknown generation signal event: {event!r}")

    await db.commit()
    await db.refresh(row)
    return row


async def record_share_signal(generation_id: str) -> None:
    """Best-effort, fire-and-forget variant used by routers/share.py — sets
    `was_shared=True` without needing the caller to thread a request-scoped
    DB session through (mirrors store_generated_itinerary's own-session
    discipline for background writes). A failure here must never affect
    share-link creation."""
    try:
        async with AsyncSessionLocal() as db:
            await record_generation_signal(db, generation_id, "shared")
    except Exception:
        logger.warning("generation signal 'shared' write failed (best-effort, ignored)", exc_info=True)


async def score_ready_generation_signals(db: AsyncSession, batch_size: int) -> int:
    """Score `generated_itinerary_signals` rows whose session looks
    finished, write the result onto the matching `generated_itineraries`
    Qdrant point payload, and stamp `scored_at` so they aren't rescored.

    Fetches unscored rows oldest-first (favours rows that have been waiting
    longest) and applies `_signal_ready_to_score()` in Python rather than in
    the SQL query — SQLite (local/dev) doesn't round-trip tz-aware
    datetimes, so a `last_updated_at <= cutoff` comparison against an aware
    cutoff would be dialect-fragile; filtering in Python via the same
    helper the unit tests exercise keeps one source of truth for
    "ready" regardless of backend. Over-fetches a multiple of `batch_size`
    candidates to have enough ready rows to fill a batch even when most of
    the oldest rows aren't ready yet.

    Per-row failures (a malformed generation_id, a Qdrant write error) are
    logged and skipped rather than aborting the whole run — the same
    resilience contract as the other per-item scheduler jobs in this
    module (e.g. `_refresh_osm_pois`).

    Returns the number of rows actually scored.
    """
    from sqlalchemy import select

    from core.qdrant import get_qdrant

    candidates = (
        await db.execute(
            select(GeneratedItinerarySignal)
            .where(GeneratedItinerarySignal.scored_at.is_(None))
            .order_by(GeneratedItinerarySignal.last_updated_at.asc())
            .limit(batch_size * 3)
        )
    ).scalars().all()

    now = datetime.now(UTC)
    scored_count = 0
    client = get_qdrant()

    for row in candidates:
        if scored_count >= batch_size:
            break
        if not _signal_ready_to_score(row, now=now):
            continue

        try:
            score = _compute_quality_score({
                "regenerated_count": row.regenerated_count,
                "session_duration_s": row.session_duration_s,
                "was_shared": row.was_shared,
                "post_gen_chat_turns": row.post_gen_chat_turns,
            })
            client.set_payload(
                collection_name=settings.qdrant_collection_generated_itineraries,
                payload={"quality_score": score},
                points=[int(row.generation_id)],
            )
        except Exception:
            logger.warning(
                "quality_score write failed for generation_id=%s (best-effort, skipped)",
                row.generation_id, exc_info=True,
            )
            continue

        row.scored_at = now
        scored_count += 1

    if scored_count:
        await db.commit()
    return scored_count


def _compute_quality_score(signals: dict) -> float:
    """Pure scoring function — no I/O, table-driven, per
    docs/rag-strategy.md's "Implicit Quality Signal Scoring" table.

    `signals` keys: regenerated_count (int), session_duration_s (int|None),
    was_shared (bool), post_gen_chat_turns (int).
    """
    score = 0.70  # baseline
    if not signals.get("regenerated_count"):
        score += 0.30
    duration = signals.get("session_duration_s")
    if duration is not None and duration > 180:
        score += 0.25
    if signals.get("was_shared"):
        score += 0.25
    if signals.get("post_gen_chat_turns", 0) > 0:
        score += 0.10
    score -= min(0.40, signals.get("regenerated_count", 0) * 0.20)
    if duration is not None and duration < 30:
        score -= 0.15
    return max(0.0, min(1.0, round(score, 2)))


def _signal_ready_to_score(row: GeneratedItinerarySignal, now: datetime | None = None) -> bool:
    """A row is ready for the scheduler to score once either: the frontend
    explicitly reported a session_duration (a real "session ended" signal),
    or nothing new has happened for `QUIET_PERIOD` (the fallback for a
    session that never got to report one)."""
    if row.session_duration_s is not None:
        return True
    now = now or datetime.now(UTC)
    last_updated = row.last_updated_at
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=UTC)
    return now - last_updated >= QUIET_PERIOD
