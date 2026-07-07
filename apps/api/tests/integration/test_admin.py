"""Integration tests for admin-only metrics and user management endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from core.analytics import log_event
from db_models import RefreshToken, User
from routers.admin import _PURGE_ALL_CONFIRMATION_PHRASE

pytestmark = pytest.mark.asyncio


async def _login(client, email: str, password: str) -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("method", "url", "kwargs"),
    [
        ("get", "/api/admin/metrics/summary", {}),
        ("get", "/api/admin/metrics/timeseries?range=7d", {}),
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
    admin = await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
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
    assert summary["cost_usage"] == {
        "gemini_requests_30d": 1,
        "gemini_tokens_30d": 321,
        "gemini_estimated_cost_usd_30d": 0.1234,
        "pexels_calls_30d": 2,
    }

    today_key = datetime.now(timezone.utc).date().isoformat()
    timeseries = timeseries_response.json()
    assert timeseries["range"] == "7d"
    assert today_key in timeseries["series"]
    assert timeseries["series"][today_key]["signup"] == 1
    assert timeseries["series"][today_key]["gemini_usage"] == 1


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
