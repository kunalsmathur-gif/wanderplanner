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
from core.auth_dependency import get_current_admin_user, get_current_user
from core.config import settings
from core.email import send_admin_request_decision_email, send_admin_request_notification
from db import get_db
from db_models import AdminRequest, Event, User
from models.auth import AdminAccessRequestCreate, AdminRequestResponse

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
            # Gemini list pricing is USD-denominated; costs are computed/stored
            # internally in USD (see core/llm_client.py) and converted to INR
            # here purely for admin-dashboard display.
            "gemini_estimated_cost_inr_30d": round(float(gemini_cost_30d or 0.0) * settings.usd_to_inr_rate, 2),
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


# ── Admin access requests ────────────────────────────────────────────────
#
# Nobody becomes an admin automatically. Signup never accepts an `is_admin`
# field (see models.auth.SignupRequest), so the *only* way a regular user's
# `is_admin` flips to True is via an existing admin approving a request
# created here. The very first admin is always seeded out-of-band (direct
# DB write) since there's no admin yet to approve one.

def _admin_request_to_response(req: AdminRequest, user: User) -> AdminRequestResponse:
    return AdminRequestResponse(
        id=str(req.id),
        user_id=str(req.user_id),
        user_email=user.email,
        user_display_name=user.display_name,
        status=req.status,
        message=req.message,
        created_at=req.created_at.isoformat(),
        reviewed_at=req.reviewed_at.isoformat() if req.reviewed_at else None,
    )


@router.post("/admin/requests", response_model=AdminRequestResponse)
async def create_admin_request(
    body: AdminAccessRequestCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdminRequestResponse:
    """Any authenticated (non-admin) user can ask to be considered for admin
    access. This never grants access by itself — it only creates a pending
    record that existing admins see in the console (and are emailed about)
    and must explicitly approve."""
    if user.is_admin:
        raise HTTPException(status_code=400, detail="You already have admin access.")

    existing = (
        await db.execute(
            select(AdminRequest).where(AdminRequest.user_id == user.id, AdminRequest.status == "pending")
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Idempotent — re-requesting while already pending just returns the
        # existing request instead of creating a duplicate.
        return _admin_request_to_response(existing, user)

    req = AdminRequest(user_id=user.id, message=body.message, status="pending")
    db.add(req)
    await db.commit()
    await db.refresh(req)

    await log_event(db, "admin_request_created", user_id=user.id)

    admin_emails = [
        row[0]
        for row in (
            await db.execute(select(User.email).where(User.is_admin.is_(True), User.email.is_not(None)))
        ).all()
    ]
    # Best-effort — email failure must never block the request itself.
    await send_admin_request_notification(
        admin_emails=admin_emails,
        requester_email=user.email or "(no email)",
        requester_name=user.display_name,
        admin_console_url=f"{settings.frontend_base_url}/admin",
    )

    return _admin_request_to_response(req, user)


@router.get("/admin/requests/me", response_model=Optional[AdminRequestResponse])
async def my_admin_request(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Optional[AdminRequestResponse]:
    """Lets the account-settings page show 'request pending / declined' UI
    without granting anything — read-only lookup of the caller's own most
    recent request."""
    req = (
        await db.execute(
            select(AdminRequest).where(AdminRequest.user_id == user.id).order_by(AdminRequest.created_at.desc())
        )
    ).scalars().first()
    if req is None:
        return None
    return _admin_request_to_response(req, user)


@router.get("/admin/requests", response_model=list[AdminRequestResponse])
async def list_admin_requests(
    status_filter: str = Query(default="pending", alias="status", pattern="^(pending|approved|rejected|all)$"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> list[AdminRequestResponse]:
    stmt = select(AdminRequest, User).join(User, User.id == AdminRequest.user_id).order_by(AdminRequest.created_at.desc())
    if status_filter != "all":
        stmt = stmt.where(AdminRequest.status == status_filter)
    rows = (await db.execute(stmt)).all()
    return [_admin_request_to_response(req, user) for req, user in rows]


@router.post("/admin/requests/{request_id}/approve", response_model=AdminRequestResponse)
async def approve_admin_request(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> AdminRequestResponse:
    req = (await db.execute(select(AdminRequest).where(AdminRequest.id == request_id))).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Admin request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {req.status}, cannot re-approve.")

    target = (await db.execute(select(User).where(User.id == req.user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Requesting user no longer exists")

    target.is_admin = True
    req.status = "approved"
    req.reviewed_by = admin.id
    req.reviewed_at = datetime.now(timezone.utc)
    await db.commit()

    await log_event(db, "admin_request_approved", user_id=admin.id, metadata={"target_user_id": str(target.id)})
    _log.warning("Admin %s approved admin access for user %s", admin.id, target.id)

    if target.email:
        await send_admin_request_decision_email(to_email=target.email, approved=True)

    return _admin_request_to_response(req, target)


@router.post("/admin/requests/{request_id}/reject", response_model=AdminRequestResponse)
async def reject_admin_request(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> AdminRequestResponse:
    req = (await db.execute(select(AdminRequest).where(AdminRequest.id == request_id))).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Admin request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {req.status}, cannot re-reject.")

    target = (await db.execute(select(User).where(User.id == req.user_id))).scalar_one_or_none()

    req.status = "rejected"
    req.reviewed_by = admin.id
    req.reviewed_at = datetime.now(timezone.utc)
    await db.commit()

    await log_event(db, "admin_request_rejected", user_id=admin.id, metadata={"target_user_id": str(req.user_id)})
    _log.info("Admin %s rejected admin access request for user %s", admin.id, req.user_id)

    if target is not None and target.email:
        await send_admin_request_decision_email(to_email=target.email, approved=False)

    return _admin_request_to_response(req, target if target is not None else User(id=req.user_id))
