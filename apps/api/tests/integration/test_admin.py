"""Integration tests for admin-only metrics and user management endpoints."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from core.analytics import log_event
from db_models import AgentLead, ItineraryFeedback, RefreshToken, User
from routers.admin import _PURGE_ALL_CONFIRMATION_PHRASE

pytestmark = pytest.mark.asyncio


async def _login(client, email: str, password: str) -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


async def _create_lead(
    db_session_maker,
    *,
    destination: str,
    created_at: datetime,
    email: str = "lead@example.com",
    responded_at: datetime | None = None,
    escalated_at: datetime | None = None,
    reassurance_sent_at: datetime | None = None,
    marked_booked_at: datetime | None = None,
):
    async with db_session_maker() as session:
        lead = AgentLead(
            email=email,
            destination=destination,
            trip_config_summary={"pax": 2},
            created_at=created_at,
            responded_at=responded_at,
            escalated_at=escalated_at,
            reassurance_sent_at=reassurance_sent_at,
            marked_booked_at=marked_booked_at,
        )
        session.add(lead)
        await session.commit()
        await session.refresh(lead)
        return lead


async def _create_feedback(
    db_session_maker,
    *,
    destination: str,
    sentiment: str,
    scope: str = "itinerary",
    created_at: datetime | None = None,
):
    async with db_session_maker() as session:
        feedback = ItineraryFeedback(
            trip_config_snapshot={"destination": {"city": destination}},
            scope=scope,
            sentiment=sentiment,
            created_at=created_at or datetime.now(UTC),
        )
        session.add(feedback)
        await session.commit()
        await session.refresh(feedback)
        return feedback


@pytest.mark.parametrize(
    ("method", "url", "kwargs"),
    [
        ("get", "/api/admin/metrics/summary", {}),
        ("get", "/api/admin/metrics/timeseries?range=7d", {}),
        ("get", "/api/admin/leads", {}),
        ("post", f"/api/admin/leads/{uuid.uuid4()}/mark-booked", {}),
        ("delete", f"/api/admin/users/{uuid.uuid4()}", {}),
        ("post", "/api/admin/users/purge-all", {"json": {"confirm": _PURGE_ALL_CONFIRMATION_PHRASE}}),
    ],
)
async def test_admin_routes_require_authentication(method, url, kwargs, client):
    response = await getattr(client, method)(url, **kwargs)
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "url", "kwargs"),
    [
        ("get", "/api/admin/metrics/summary", {}),
        ("get", "/api/admin/metrics/timeseries?range=7d", {}),
        ("get", "/api/admin/leads", {}),
        ("post", f"/api/admin/leads/{uuid.uuid4()}/mark-booked", {}),
        ("delete", f"/api/admin/users/{uuid.uuid4()}", {}),
        ("post", "/api/admin/users/purge-all", {"json": {"confirm": _PURGE_ALL_CONFIRMATION_PHRASE}}),
    ],
)
async def test_admin_routes_forbid_non_admin_users(method, url, kwargs, client, user_factory):
    await user_factory(email="member@example.com", password="Password123!")
    await _login(client, "member@example.com", "Password123!")

    response = await getattr(client, method)(url, **kwargs)
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


async def test_admin_metrics_summary_and_timeseries_return_expected_data(
    client,
    db_session_maker,
    user_factory,
):
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    member = await user_factory(email="member@example.com", password="Password123!")
    await _login(client, "admin@example.com", "Password123!")

    async with db_session_maker() as session:
        await log_event(session, "signup", user_id=member.id, metadata={"provider": "password"})
        await log_event(session, "session_start")
        await log_event(session, "login_success", user_id=member.id, metadata={"provider": "password"})
        await log_event(session, "login_failed", metadata={"email_domain": "example.com"})
        await log_event(session, "itinerary_generated", user_id=member.id)
        await log_event(session, "itinerary_failed", user_id=member.id, metadata={"reason": "timeout"})
        await log_event(
            session,
            "gemini_usage",
            user_id=member.id,
            metadata={"total_tokens": 321, "total_cost_usd": 0.1234},
        )
        await log_event(session, "pexels_usage", user_id=member.id, metadata={"call_count": 2})

    summary_response = await client.get("/api/admin/metrics/summary")
    timeseries_response = await client.get("/api/admin/metrics/timeseries", params={"range": "7d"})

    assert summary_response.status_code == 200
    assert timeseries_response.status_code == 200

    summary = summary_response.json()
    assert summary["total_users"] == 2
    assert summary["signups"] == {"today": 1, "7d": 1, "30d": 1}
    assert summary["sessions"] == {"today": 1, "7d": 1, "30d": 1}
    assert summary["logins"]["success_30d"] == 2
    assert summary["logins"]["failed_30d"] == 1
    assert summary["logins"]["success_rate_30d"] == pytest.approx(2 / 3)
    assert summary["itineraries"] == {"generated_30d": 1, "failed_30d": 1}
    from core.config import settings as _settings

    assert summary["cost_usage"]["gemini_requests_30d"] == 1
    assert summary["cost_usage"]["gemini_tokens_30d"] == 321
    assert summary["cost_usage"]["gemini_estimated_cost_inr_30d"] == pytest.approx(
        round(0.1234 * _settings.usd_to_inr_rate, 2)
    )
    assert summary["cost_usage"]["pexels_calls_30d"] == 2

    today_key = datetime.now(UTC).date().isoformat()
    timeseries = timeseries_response.json()
    assert timeseries["range"] == "7d"
    assert today_key in timeseries["series"]
    assert timeseries["series"][today_key]["signup"] == 1
    assert timeseries["series"][today_key]["gemini_usage"] == 1


async def test_admin_metrics_summary_defaults_agent_leads_to_zero_when_empty(
    client,
    user_factory,
):
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    await _login(client, "admin@example.com", "Password123!")

    response = await client.get("/api/admin/metrics/summary")

    assert response.status_code == 200
    assert response.json()["agent_leads"] == {
        "created_total": 0,
        "responded_total": 0,
        "escalated_total": 0,
        "reassurance_sent_total": 0,
        "response_time_avg_hours": None,
        "response_time_p50_hours": None,
        "response_time_p90_hours": None,
        "sla_breach_rate": None,
        "marked_booked_total": 0,
        "top_destinations": [],
    }


async def test_admin_agent_lead_metrics_and_timeseries_include_summary_math(
    client,
    db_session_maker,
    user_factory,
):
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    await _login(client, "admin@example.com", "Password123!")

    now = datetime.now(UTC)
    for index in range(10):
        created_at = now - timedelta(days=1, hours=index)
        responded_at = None
        escalated_at = None
        reassurance_sent_at = None
        marked_booked_at = None
        if index < 3:
            responded_at = created_at + timedelta(hours=index + 2)
        if index in {3, 4}:
            escalated_at = created_at + timedelta(hours=24)
        if index == 5:
            reassurance_sent_at = created_at + timedelta(hours=48)
        if index in {0, 6}:
            marked_booked_at = created_at + timedelta(hours=12)
        await _create_lead(
            db_session_maker,
            destination="Kyoto" if index < 6 else "Bali",
            email=f"lead-{index}@example.com",
            created_at=created_at,
            responded_at=responded_at,
            escalated_at=escalated_at,
            reassurance_sent_at=reassurance_sent_at,
            marked_booked_at=marked_booked_at,
        )

    async with db_session_maker() as session:
        await log_event(
            session,
            "agent_lead_created",
            metadata={"lead_id": "lead-1", "destination": "Kyoto"},
        )

    summary_response = await client.get("/api/admin/metrics/summary")
    timeseries_response = await client.get("/api/admin/metrics/timeseries", params={"range": "30d"})

    assert summary_response.status_code == 200
    assert timeseries_response.status_code == 200

    summary = summary_response.json()["agent_leads"]
    assert summary["created_total"] == 10
    assert summary["responded_total"] == 3
    assert summary["escalated_total"] == 2
    assert summary["reassurance_sent_total"] == 1
    assert summary["marked_booked_total"] == 2
    assert summary["sla_breach_rate"] == pytest.approx(0.2)
    assert summary["response_time_avg_hours"] == pytest.approx(3.0)
    assert summary["response_time_p50_hours"] == pytest.approx(3.0)
    assert summary["response_time_p90_hours"] == pytest.approx(4.0)
    assert summary["top_destinations"][0] == {"destination": "Kyoto", "count": 6}
    assert summary["top_destinations"][1] == {"destination": "Bali", "count": 4}

    response_day_key = (now - timedelta(days=1) + timedelta(hours=2)).date().isoformat()
    timeseries = timeseries_response.json()["series"]
    assert timeseries[now.date().isoformat()]["agent_lead_created"] == 1
    assert timeseries[response_day_key]["agent_lead_response_avg_hours"] == pytest.approx(3.0)


async def test_admin_metrics_summary_defaults_itinerary_feedback_to_zero_when_empty(
    client,
    user_factory,
):
    """FEEDBACK-007."""
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    await _login(client, "admin@example.com", "Password123!")

    response = await client.get("/api/admin/metrics/summary")

    assert response.status_code == 200
    assert response.json()["itinerary_feedback"] == {
        "total": 0,
        "negative_total": 0,
        "negative_rate": None,
        "by_destination": [],
    }


async def test_admin_metrics_reports_negative_feedback_rate_by_destination(
    client,
    db_session_maker,
    user_factory,
):
    """FEEDBACK-006."""
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    await _login(client, "admin@example.com", "Password123!")

    await _create_feedback(db_session_maker, destination="Kyoto", sentiment="missed_the_mark")
    await _create_feedback(db_session_maker, destination="Kyoto", sentiment="thumbs_down", scope="place")
    await _create_feedback(db_session_maker, destination="Kyoto", sentiment="thumbs_up", scope="place")
    await _create_feedback(db_session_maker, destination="Bali", sentiment="thumbs_up", scope="day")
    await _create_feedback(db_session_maker, destination="Bali", sentiment="thumbs_up", scope="day")

    response = await client.get("/api/admin/metrics/summary")
    assert response.status_code == 200

    summary = response.json()["itinerary_feedback"]
    assert summary["total"] == 5
    assert summary["negative_total"] == 2
    assert summary["negative_rate"] == pytest.approx(0.4)

    by_destination = {row["destination"]: row for row in summary["by_destination"]}
    assert by_destination["Kyoto"]["total"] == 3
    assert by_destination["Kyoto"]["negative_total"] == 2
    # The API rounds to 4 decimals (0.6667), which differs from the raw
    # fraction (0.666666...) by more than pytest.approx's default tolerance.
    assert by_destination["Kyoto"]["negative_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert by_destination["Bali"]["total"] == 2
    assert by_destination["Bali"]["negative_total"] == 0
    assert by_destination["Bali"]["negative_rate"] == 0.0


async def test_admin_can_list_and_mark_leads_booked_idempotently(
    client,
    db_session_maker,
    user_factory,
):
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    lead = await _create_lead(
        db_session_maker,
        destination="Paris",
        created_at=datetime.now(UTC) - timedelta(hours=2),
    )
    await _login(client, "admin@example.com", "Password123!")

    list_response = await client.get("/api/admin/leads")
    first_mark = await client.post(f"/api/admin/leads/{lead.id}/mark-booked")
    second_mark = await client.post(f"/api/admin/leads/{lead.id}/mark-booked")

    assert list_response.status_code == 200
    assert list_response.json()[0]["status"] == "pending"
    assert first_mark.status_code == 200
    assert second_mark.status_code == 200
    assert first_mark.json()["marked_booked_at"] is not None
    assert second_mark.json()["marked_booked_at"] == first_mark.json()["marked_booked_at"]


async def test_admin_can_mark_lead_responded_idempotently_and_independently_of_booked(
    client,
    db_session_maker,
    user_factory,
):
    """Two distinct CTAs: "responded" tracks SLA (stops the escalation clock),
    "booked" tracks revenue/conversion \u2014 marking one must not set the other."""
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    lead = await _create_lead(
        db_session_maker,
        destination="Lisbon",
        created_at=datetime.now(UTC) - timedelta(hours=2),
    )
    await _login(client, "admin@example.com", "Password123!")

    first_mark = await client.post(f"/api/admin/leads/{lead.id}/mark-responded")
    second_mark = await client.post(f"/api/admin/leads/{lead.id}/mark-responded")

    assert first_mark.status_code == 200
    assert second_mark.status_code == 200
    assert first_mark.json()["responded_at"] is not None
    assert first_mark.json()["status"] == "responded"
    assert second_mark.json()["responded_at"] == first_mark.json()["responded_at"]
    assert first_mark.json()["marked_booked_at"] is None


async def test_admin_delete_user_prevents_self_delete_and_cascades_refresh_tokens(
    client,
    db_session_maker,
    refresh_token_factory,
    user_factory,
):
    admin = await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    target = await user_factory(email="target@example.com", password="Password123!")
    await refresh_token_factory(user_id=target.id)
    await _login(client, "admin@example.com", "Password123!")

    self_delete_response = await client.delete(f"/api/admin/users/{admin.id}")
    delete_response = await client.delete(f"/api/admin/users/{target.id}")

    assert self_delete_response.status_code == 400
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "deleted", "user_id": str(target.id)}

    async with db_session_maker() as session:
        assert await session.get(User, target.id) is None
        remaining_tokens = (
            await session.execute(select(RefreshToken).where(RefreshToken.user_id == target.id))
        ).scalars().all()
        assert remaining_tokens == []


async def test_admin_purge_all_requires_exact_phrase_and_preserves_admins(
    client,
    db_session_maker,
    user_factory,
):
    admin = await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    await user_factory(email="member-one@example.com")
    await user_factory(email="member-two@example.com")
    await _login(client, "admin@example.com", "Password123!")

    wrong_confirm = await client.post(
        "/api/admin/users/purge-all",
        json={"confirm": "DELETE USERS"},
    )
    assert wrong_confirm.status_code == 400

    async with db_session_maker() as session:
        before_count = (
            await session.execute(select(func.count()).select_from(User).where(User.is_admin.is_(False)))
        ).scalar_one()
        assert before_count == 2

    purge_response = await client.post(
        "/api/admin/users/purge-all",
        json={"confirm": _PURGE_ALL_CONFIRMATION_PHRASE},
    )

    assert purge_response.status_code == 200
    assert purge_response.json() == {"status": "purged", "deleted_count": 2}

    async with db_session_maker() as session:
        total_users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        remaining_admins = (
            await session.execute(select(func.count()).select_from(User).where(User.is_admin.is_(True)))
        ).scalar_one()
        assert total_users == 1
        assert remaining_admins == 1
        assert await session.get(User, admin.id) is not None
