"""Admin-only analytics endpoints — technical + business metrics.

Everything here is gated by `get_current_admin_user`: a regular authenticated
user gets a 403, not a 401, so the frontend can distinguish "please log in"
from "you're logged in but not allowed here."
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.analytics import log_event
from core.auth_dependency import get_current_admin_user
from db import get_db
from db_models import Event, User

router = APIRouter()
_log = logging.getLogger("wanderplanner.admin")

# Bulk-purge is intentionally guarded by a typed confirmation phrase (not
# just a button click) — this permanently deletes every non-admin user
# account and cannot be undone.
_PURGE_ALL_CONFIRMATION_PHRASE = "DELETE ALL USERS"


async def _count_events(db: AsyncSession, event_type: str, since: Optional[datetime] = None) -> int:
    stmt = select(func.count()).select_from(Event).where(Event.event_type == event_type)
    if since is not None:
        stmt = stmt.where(Event.created_at >= since)
    return (await db.execute(stmt)).scalar_one()


@router.get("/admin/metrics/summary")
async def metrics_summary(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)

    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()

    signups_today = await _count_events(db, "signup", today_start)
    signups_7d = await _count_events(db, "signup", d7)
    signups_30d = await _count_events(db, "signup", d30)

    sessions_today = await _count_events(db, "session_start", today_start)
    sessions_7d = await _count_events(db, "session_start", d7)
    sessions_30d = await _count_events(db, "session_start", d30)

    login_success_30d = await _count_events(db, "login_success", d30)
    login_failed_30d = await _count_events(db, "login_failed", d30)
    login_total = login_success_30d + login_failed_30d
    login_success_rate = (login_success_30d / login_total) if login_total else None

    itineraries_generated_30d = await _count_events(db, "itinerary_generated", d30)
    itineraries_failed_30d = await _count_events(db, "itinerary_failed", d30)

    # Gemini token/cost usage — each `gemini_usage` event is logged once per
    # request (see core/analytics.flush_llm_usage) and already aggregates
    # every Gemini call made during that request, so summing its
    # `total_tokens`/`total_cost_usd` fields gives the true 30-day totals.
    gemini_stmt = select(
        func.count(),
        func.coalesce(func.sum(Event.event_metadata["total_tokens"].as_integer()), 0),
        func.coalesce(func.sum(Event.event_metadata["total_cost_usd"].as_float()), 0.0),
    ).where(Event.event_type == "gemini_usage", Event.created_at >= d30)
    gemini_requests_30d, gemini_tokens_30d, gemini_cost_30d = (await db.execute(gemini_stmt)).one()

    pexels_stmt = select(
        func.coalesce(func.sum(Event.event_metadata["call_count"].as_integer()), 0),
    ).where(Event.event_type == "pexels_usage", Event.created_at >= d30)
    pexels_calls_30d = (await db.execute(pexels_stmt)).scalar_one()

    return {
        "total_users": total_users,
        "signups": {"today": signups_today, "7d": signups_7d, "30d": signups_30d},
        "sessions": {"today": sessions_today, "7d": sessions_7d, "30d": sessions_30d},
        "logins": {
            "success_30d": login_success_30d,
            "failed_30d": login_failed_30d,
            "success_rate_30d": login_success_rate,
        },
        "itineraries": {
            "generated_30d": itineraries_generated_30d,
            "failed_30d": itineraries_failed_30d,
        },
        "cost_usage": {
            "gemini_requests_30d": gemini_requests_30d,
            "gemini_tokens_30d": int(gemini_tokens_30d or 0),
            "gemini_estimated_cost_usd_30d": round(float(gemini_cost_30d or 0.0), 4),
            "pexels_calls_30d": int(pexels_calls_30d or 0),
        },
    }


@router.get("/admin/metrics/timeseries")
async def metrics_timeseries(
    range: str = Query(default="30d", pattern="^(7d|30d)$"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    days = 7 if range == "7d" else 30
    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(
            func.date(Event.created_at).label("day"),
            Event.event_type,
            func.count().label("count"),
        )
        .where(Event.created_at >= since)
        .group_by("day", Event.event_type)
        .order_by("day")
    )
    rows = (await db.execute(stmt)).all()

    series: dict[str, dict[str, int]] = {}
    for day, event_type, count in rows:
        # SQLite's date() returns a str already; Postgres' date() returns a
        # date object — normalize both to an ISO "YYYY-MM-DD" string.
        key = day if isinstance(day, str) else day.isoformat()
        series.setdefault(key, {})[event_type] = count

    return {"range": range, "series": series}


class PurgeAllRequest(BaseModel):
    confirm: str


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> dict:
    """Bulk/single-target data purge — permanently deletes one user's
    account and personal data (their `refresh_tokens` cascade-delete;
    their `events` rows are anonymized via `user_id` -> NULL, not deleted,
    so aggregate analytics survive). Distinct from the self-service
    `DELETE /auth/me` endpoint, which a user calls on their own behalf.
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="Use your own account settings to delete your own account, not this endpoint.",
        )

    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(target)
    await db.commit()
    await log_event(db, "admin_user_deleted", user_id=admin.id, metadata={"deleted_user_id": str(user_id)})
    _log.warning("Admin %s deleted user %s", admin.id, user_id)
    return {"status": "deleted", "user_id": str(user_id)}


@router.post("/admin/users/purge-all")
async def purge_all_users(
    body: PurgeAllRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> dict:
    """Bulk data purge — permanently deletes every non-admin user account in
    one go, for org-wide "delete all user data" compliance requests. Guarded
    by a typed confirmation phrase (not just a button) since this is
    irreversible and affects every user at once. Admin accounts are never
    deleted by this endpoint (delete them individually via the single-user
    endpoint if truly needed, to avoid a bulk request accidentally locking
    everyone out)."""
    if body.confirm != _PURGE_ALL_CONFIRMATION_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f'Type "{_PURGE_ALL_CONFIRMATION_PHRASE}" exactly to confirm this irreversible action.',
        )

    count_stmt = select(func.count()).select_from(User).where(User.is_admin.is_(False))
    deleted_count = (await db.execute(count_stmt)).scalar_one()

    await db.execute(delete(User).where(User.is_admin.is_(False)))
    await db.commit()

    await log_event(db, "admin_purge_all", user_id=admin.id, metadata={"deleted_count": deleted_count})
    _log.warning("Admin %s bulk-purged %d user accounts", admin.id, deleted_count)
    return {"status": "purged", "deleted_count": deleted_count}
