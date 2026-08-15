"""Per-user "resume last itinerary" persistence (issue #65).

Stores only the single most recent successfully-generated itinerary per
logged-in user — an upsert onto `user_last_itinerary`, never a history list
— so the Account page and Anya's "continue my trip" intent can hand the
user straight back into the existing wizard/edit flow after they navigate
away, refresh, or come back later.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import AsyncSessionLocal
from db_models import UserLastItinerary
from models.itinerary import ItineraryResponse
from models.trip import TripConfig

logger = logging.getLogger(__name__)

# A saved itinerary older than this is treated as gone: the "continue your
# last trip" card/intent stops surfacing it and a stale plan for
# since-passed dates doesn't linger indefinitely. 30 days, not a hard cron
# job — expiry is checked lazily on read (see `get_user_last_itinerary`),
# which is enough for a single-row-per-user upsert with no history to prune.
USER_LAST_ITINERARY_TTL = timedelta(days=30)


def _as_utc(value: datetime) -> datetime:
    """Treat a naive stored timestamp as UTC — SQLite (local/dev) doesn't
    round-trip tz-aware datetimes, so a comparison against an aware `now()`
    would otherwise raise. Same helper as `routers/auth.py::_as_utc`."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def store_user_last_itinerary(
    user_id: uuid.UUID, trip_config: TripConfig, itinerary: ItineraryResponse
) -> None:
    """Best-effort upsert of a user's most recent generated itinerary.

    Never raises — a write failure here must never affect the itinerary
    already streamed to the client. Call this via `asyncio.create_task` at
    the call site (not awaited inline), same fire-and-forget discipline as
    `services/generated_itineraries.py::store_generated_itinerary`. Opens
    its own DB session rather than reusing the request-scoped one, since a
    fire-and-forget task can legitimately still be running after the
    request (and its session) has finished.
    """
    try:
        async with AsyncSessionLocal() as db:
            row = await db.get(UserLastItinerary, user_id)
            trip_config_json = trip_config.model_dump(mode="json")
            itinerary_json = itinerary.model_dump(mode="json")
            if row is None:
                db.add(
                    UserLastItinerary(
                        user_id=user_id,
                        trip_config_json=trip_config_json,
                        itinerary_json=itinerary_json,
                    )
                )
            else:
                row.trip_config_json = trip_config_json
                row.itinerary_json = itinerary_json
            await db.commit()
    except Exception:
        logger.warning("user_last_itinerary write failed (best-effort, ignored)", exc_info=True)


async def get_user_last_itinerary(db: AsyncSession, user_id: uuid.UUID) -> UserLastItinerary | None:
    """Fetch the caller's saved last itinerary row, or None if they have
    none yet or it has aged past `USER_LAST_ITINERARY_TTL` — the normal
    (non-fire-and-forget) request-scoped session is used here since this
    backs a synchronous GET response.

    An expired row is deleted on the way out (lazy cleanup, no separate
    cron job needed for a single-row-per-user table) rather than left
    behind to be silently overwritten by the next generation anyway.
    """
    row = (
        await db.execute(select(UserLastItinerary).where(UserLastItinerary.user_id == user_id))
    ).scalar_one_or_none()
    if row is None:
        return None
    if datetime.now(UTC) - _as_utc(row.updated_at) > USER_LAST_ITINERARY_TTL:
        await db.delete(row)
        await db.commit()
        return None
    return row
