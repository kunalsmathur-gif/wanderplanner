"""Admin-only analytics endpoints — technical + business metrics.

Everything here is gated by `get_current_admin_user`: a regular authenticated
user gets a 403, not a 401, so the frontend can distinguish "please log in"
from "you're logged in but not allowed here."
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.analytics import log_event
from core.auth_dependency import get_current_admin_user, get_current_user
from core.config import settings
from core.email import send_admin_request_decision_email, send_admin_request_notification
from db import get_db
from db_models import AdminRequest, AgentLead, Event, ItineraryFeedback, User
from models.agent_leads import AgentLeadAdminResponse
from models.auth import AdminAccessRequestCreate, AdminRequestResponse

router = APIRouter()
_log = logging.getLogger("wanderplanner.admin")

# Bulk-purge is intentionally guarded by a typed confirmation phrase (not
# just a button click) — this permanently deletes every non-admin user
# account and cannot be undone.
_PURGE_ALL_CONFIRMATION_PHRASE = "DELETE ALL USERS"


async def _count_events(db: AsyncSession, event_type: str, since: datetime | None = None) -> int:
    stmt = select(func.count()).select_from(Event).where(Event.event_type == event_type)
    if since is not None:
        stmt = stmt.where(Event.created_at >= since)
    return (await db.execute(stmt)).scalar_one()


async def _event_durations_ms(db: AsyncSession, event_type: str, since: datetime) -> list[float]:
    """Every `duration_ms` value logged against `event_type` since `since`,
    for latency aggregation (avg/p50/p90) in `metrics_summary`. Fetched as a
    plain Python list (like `response_times` below) rather than a SQL AVG so
    the same `_percentile()` helper can be reused for both — `duration_ms`
    is only present on events logged after this instrumentation shipped, so
    older rows (null) are naturally excluded by the `isnot(None)` filter."""
    stmt = (
        select(Event.event_metadata["duration_ms"].as_float())
        .where(
            Event.event_type == event_type,
            Event.created_at >= since,
            Event.event_metadata["duration_ms"].isnot(None),
        )
    )
    return [v for v in (await db.execute(stmt)).scalars().all() if v is not None]


def _lead_response_time_hours(lead: AgentLead) -> float | None:
    if lead.responded_at is None:
        return None
    return round((lead.responded_at - lead.created_at).total_seconds() / 3600, 2)


def _as_utc(value: datetime) -> datetime:
    """SQLite (the test DB) drops tzinfo on round-trip while Postgres keeps it,
    so a naive value here means "already UTC", not "local time"."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _lead_sla_breached(lead: AgentLead) -> bool:
    """Did this lead blow the promised-reply window?

    For an answered lead the clock stops at `responded_at`; for one still
    open it runs to now, so a lead flips to breached the moment the window
    passes rather than only once someone finally replies.
    """
    deadline = _as_utc(lead.created_at) + timedelta(hours=settings.agent_lead_escalation_hours)
    stopped_at = _as_utc(lead.responded_at) if lead.responded_at is not None else datetime.now(UTC)
    return stopped_at > deadline


def _lead_status(lead: AgentLead) -> str:
    """Collapses the four lifecycle timestamps into one badge label.

    Answering a lead does not erase the fact that it was answered late —
    the old version returned a flat "responded" here, which made a reply at
    2 hours and a reply at 100 hours indistinguishable in the dashboard and
    hid every SLA breach the moment it was cleaned up.

    Escalation and breach are checked separately on purpose: the escalation
    job only runs on its own interval (`agent_lead_sla_check_hours`), so a
    lead answered shortly after the deadline can breach without ever having
    been escalated. Either one is enough to call the response late.
    """
    if lead.responded_at is not None:
        if lead.escalated_at is not None or _lead_sla_breached(lead):
            return "responded_late"
        return "responded"
    if lead.reassurance_sent_at is not None:
        return "reassured"
    if lead.escalated_at is not None:
        return "escalated"
    return "pending"


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 2)


def _lead_to_response(lead: AgentLead) -> AgentLeadAdminResponse:
    return AgentLeadAdminResponse(
        id=str(lead.id),
        user_id=str(lead.user_id) if lead.user_id else None,
        email=lead.email,
        destination=lead.destination,
        source=lead.source,
        trip_config_summary=lead.trip_config_summary,
        custom_notes=lead.custom_notes,
        created_at=lead.created_at.isoformat(),
        responded_at=lead.responded_at.isoformat() if lead.responded_at else None,
        escalated_at=lead.escalated_at.isoformat() if lead.escalated_at else None,
        reassurance_sent_at=lead.reassurance_sent_at.isoformat() if lead.reassurance_sent_at else None,
        marked_booked_at=lead.marked_booked_at.isoformat() if lead.marked_booked_at else None,
        status=_lead_status(lead),
        response_time_hours=_lead_response_time_hours(lead),
        sla_breached=_lead_sla_breached(lead),
        was_escalated=lead.escalated_at is not None,
    )


@router.get("/admin/metrics/summary")
async def metrics_summary(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    now = datetime.now(UTC)
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

    # Latency metrics (issue: prod itinerary-generation timeouts) — average +
    # p50/p90 wall-clock duration for the two LLM-backed request paths that
    # actually matter for perceived speed. Only successful requests are
    # included (matches how `duration_ms` is logged — see
    # routers/itinerary.py / routers/feasibility.py); failed/timed-out
    # requests are already visible separately via the failure counts above.
    itinerary_durations_ms = await _event_durations_ms(db, "itinerary_generated", d30)
    feasibility_durations_ms = await _event_durations_ms(db, "feasibility_checked", d30)

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

    recent_leads = (
        await db.execute(select(AgentLead).where(AgentLead.created_at >= d30))
    ).scalars().all()
    response_times = [
        response_time
        for lead in recent_leads
        if (response_time := _lead_response_time_hours(lead)) is not None
    ]
    created_total = len(recent_leads)
    responded_total = sum(1 for lead in recent_leads if lead.responded_at is not None)
    escalated_total = sum(1 for lead in recent_leads if lead.escalated_at is not None)
    reassurance_sent_total = sum(1 for lead in recent_leads if lead.reassurance_sent_at is not None)
    marked_booked_total = sum(1 for lead in recent_leads if lead.marked_booked_at is not None)

    top_destinations_rows = (
        await db.execute(
            select(AgentLead.destination, func.count().label("count"))
            .where(AgentLead.created_at >= d30)
            .group_by(AgentLead.destination)
            .order_by(func.count().desc(), AgentLead.destination.asc())
            .limit(5)
        )
    ).all()

    # Feedback volume + negative-feedback rate by destination — the concrete
    # "which destinations/data to improve next" signal, per the PRD's user-
    # feedback plan (issue #64). Aggregated in Python, same as the leads
    # block above: trip_config_snapshot is a JSON blob and destination
    # extraction needs to be JSON-shape-tolerant (dict, or already a bare
    # string) rather than relying on a DB-specific JSON path operator.
    recent_feedback = (
        await db.execute(select(ItineraryFeedback).where(ItineraryFeedback.created_at >= d30))
    ).scalars().all()

    def _feedback_destination(feedback: ItineraryFeedback) -> str:
        snapshot = feedback.trip_config_snapshot or {}
        destination = snapshot.get("destination")
        if isinstance(destination, dict):
            return destination.get("city") or "Unknown"
        return destination or "Unknown"

    _NEGATIVE_SENTIMENTS = {"missed_the_mark", "thumbs_down"}

    feedback_total = len(recent_feedback)
    feedback_negative_total = sum(1 for f in recent_feedback if f.sentiment in _NEGATIVE_SENTIMENTS)

    feedback_by_destination: dict[str, dict[str, int]] = {}
    for f in recent_feedback:
        dest = _feedback_destination(f)
        bucket = feedback_by_destination.setdefault(dest, {"total": 0, "negative": 0})
        bucket["total"] += 1
        if f.sentiment in _NEGATIVE_SENTIMENTS:
            bucket["negative"] += 1

    # Qdrant Cloud free-tier RAM headroom — same estimate core/scheduler.py's
    # periodic job logs a WARNING/ERROR for; surfaced here too so an admin can
    # see current usage without digging through logs. Best-effort: a Qdrant
    # outage shouldn't take down the whole summary endpoint.
    qdrant_storage = None
    try:
        from core.qdrant import estimate_storage_usage, get_qdrant
        if settings.qdrant_url != ":memory:":
            usage = estimate_storage_usage(get_qdrant())
            qdrant_storage = {
                "estimated_used_mb": round(usage["total_estimated_bytes"] / (1024 * 1024), 1),
                "limit_mb": round(usage["limit_bytes"] / (1024 * 1024), 1),
                "used_fraction": round(usage["used_fraction"], 3) if usage["used_fraction"] is not None else None,
                "collections": {
                    name: {
                        "points_count": d["points_count"],
                        "estimated_mb": round(d["estimated_bytes"] / (1024 * 1024), 1),
                    }
                    for name, d in usage["collections"].items()
                },
            }
    except Exception as e:
        _log.warning("Qdrant storage estimate failed for admin summary: %s", e)

    # Redis memory headroom — same numbers core/scheduler.py's periodic job
    # logs for; None when running the local in-process dict fallback (no
    # REDIS_URL) or if the Redis call itself fails.
    redis_storage = None
    try:
        if settings.redis_url:
            from core.redis_client import get_cache
            cache = get_cache()
            used_bytes = await cache.memory_usage_bytes()
            key_count = await cache.key_count()
            if used_bytes is not None:
                limit_bytes = settings.redis_memory_limit_bytes
                redis_storage = {
                    "estimated_used_mb": round(used_bytes / (1024 * 1024), 1),
                    "limit_mb": round(limit_bytes / (1024 * 1024), 1),
                    "used_fraction": round(used_bytes / limit_bytes, 3) if limit_bytes else None,
                    "key_count": key_count,
                }
    except Exception as e:
        _log.warning("Redis memory estimate failed for admin summary: %s", e)

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
            "generation_time_avg_ms": round(sum(itinerary_durations_ms) / len(itinerary_durations_ms), 1) if itinerary_durations_ms else None,
            "generation_time_p50_ms": _percentile(itinerary_durations_ms, 0.5),
            "generation_time_p90_ms": _percentile(itinerary_durations_ms, 0.9),
        },
        "feasibility_checks": {
            "count_30d": len(feasibility_durations_ms),
            "check_time_avg_ms": round(sum(feasibility_durations_ms) / len(feasibility_durations_ms), 1) if feasibility_durations_ms else None,
            "check_time_p50_ms": _percentile(feasibility_durations_ms, 0.5),
            "check_time_p90_ms": _percentile(feasibility_durations_ms, 0.9),
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
        "agent_leads": {
            "created_total": created_total,
            "responded_total": responded_total,
            "escalated_total": escalated_total,
            "reassurance_sent_total": reassurance_sent_total,
            "response_time_avg_hours": round(sum(response_times) / len(response_times), 2) if response_times else None,
            "response_time_p50_hours": _percentile(response_times, 0.5),
            "response_time_p90_hours": _percentile(response_times, 0.9),
            "sla_breach_rate": round(escalated_total / created_total, 4) if created_total else None,
            "marked_booked_total": marked_booked_total,
            "top_destinations": [
                {"destination": destination, "count": count}
                for destination, count in top_destinations_rows
            ],
        },
        "itinerary_feedback": {
            "total": feedback_total,
            "negative_total": feedback_negative_total,
            "negative_rate": round(feedback_negative_total / feedback_total, 4) if feedback_total else None,
            "by_destination": [
                {
                    "destination": dest,
                    "total": bucket["total"],
                    "negative_total": bucket["negative"],
                    "negative_rate": round(bucket["negative"] / bucket["total"], 4) if bucket["total"] else None,
                }
                for dest, bucket in sorted(
                    feedback_by_destination.items(), key=lambda kv: kv[1]["total"], reverse=True
                )
            ],
        },
        "qdrant_storage": qdrant_storage,
        "redis_storage": redis_storage,
    }


@router.get("/admin/metrics/timeseries")
async def metrics_timeseries(
    range: str = Query(default="30d", pattern="^(7d|30d)$"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> dict:
    days = 7 if range == "7d" else 30
    since = datetime.now(UTC) - timedelta(days=days)

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

    # float, not int: event counts are integers but the
    # "agent_lead_response_avg_hours" series added below is a rounded average.
    series: dict[str, dict[str, float]] = {}
    for day, event_type, count in rows:
        # SQLite's date() returns a str already; Postgres' date() returns a
        # date object — normalize both to an ISO "YYYY-MM-DD" string.
        key = day if isinstance(day, str) else day.isoformat()
        series.setdefault(key, {})[event_type] = count

    responded_leads = (
        await db.execute(
            select(AgentLead).where(
                AgentLead.responded_at.is_not(None),
                AgentLead.responded_at >= since,
            )
        )
    ).scalars().all()
    response_times_by_day: dict[str, list[float]] = {}
    for lead in responded_leads:
        if lead.responded_at is None:
            # Unreachable via the query above (it filters `is_not(None)`), but
            # the column is nullable, so narrow rather than assert — a
            # bookkeeping metric must not 500 on an unexpected row.
            continue
        key = lead.responded_at.date().isoformat()
        response_time = _lead_response_time_hours(lead)
        if response_time is not None:
            response_times_by_day.setdefault(key, []).append(response_time)
    for key, values in response_times_by_day.items():
        series.setdefault(key, {})["agent_lead_response_avg_hours"] = round(sum(values) / len(values), 2)

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


@router.get("/admin/leads", response_model=list[AgentLeadAdminResponse])
async def list_agent_leads(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> list[AgentLeadAdminResponse]:
    leads = (
        await db.execute(
            select(AgentLead).order_by(AgentLead.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return [_lead_to_response(lead) for lead in leads]


@router.post("/admin/leads/{lead_id}/mark-responded", response_model=AgentLeadAdminResponse)
async def mark_agent_lead_responded(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> AgentLeadAdminResponse:
    """The "responded" CTA — this is the only place `responded_at` gets set,
    i.e. the SLA clock (see core/scheduler._check_agent_lead_sla) only stops
    once an admin/agent explicitly confirms they replied to the traveler.
    Distinct from `mark-booked`, which tracks revenue/conversion instead."""
    lead = (await db.execute(select(AgentLead).where(AgentLead.id == lead_id))).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    if lead.responded_at is None:
        lead.responded_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(lead)
        await log_event(
            db,
            "agent_lead_marked_responded",
            user_id=admin.id,
            metadata={"lead_id": str(lead.id), "destination": lead.destination},
        )

    return _lead_to_response(lead)


@router.post("/admin/leads/{lead_id}/mark-booked", response_model=AgentLeadAdminResponse)
async def mark_agent_lead_booked(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> AgentLeadAdminResponse:
    lead = (await db.execute(select(AgentLead).where(AgentLead.id == lead_id))).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    if lead.marked_booked_at is None:
        lead.marked_booked_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(lead)
        await log_event(
            db,
            "agent_lead_marked_booked",
            user_id=admin.id,
            metadata={"lead_id": str(lead.id), "destination": lead.destination},
        )

    return _lead_to_response(lead)


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


@router.get("/admin/requests/me", response_model=AdminRequestResponse | None)
async def my_admin_request(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdminRequestResponse | None:
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
    req.reviewed_at = datetime.now(UTC)
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
    req.reviewed_at = datetime.now(UTC)
    await db.commit()

    await log_event(db, "admin_request_rejected", user_id=admin.id, metadata={"target_user_id": str(req.user_id)})
    _log.info("Admin %s rejected admin access request for user %s", admin.id, req.user_id)

    if target is not None and target.email:
        await send_admin_request_decision_email(to_email=target.email, approved=False)

    return _admin_request_to_response(req, target if target is not None else User(id=req.user_id))
