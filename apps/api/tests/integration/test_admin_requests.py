"""Integration tests for the admin-access-request approval workflow.

Nobody becomes an admin automatically (signup never accepts an `is_admin`
field). The only supported path to gaining admin access post-signup is:
1. an authenticated user calls POST /api/admin/requests
2. an existing admin sees it (GET /api/admin/requests) and either approves
   or rejects it
3. approval flips is_admin=True on the target user; rejection does not
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio


async def _login(client, email: str, password: str) -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


@patch("routers.admin.send_admin_request_notification", new_callable=AsyncMock)
async def test_non_admin_can_create_admin_request(mock_notify, client, user_factory):
    mock_notify.return_value = True
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    await user_factory(email="member@example.com", password="Password123!")
    await _login(client, "member@example.com", "Password123!")

    response = await client.post("/api/admin/requests", json={"message": "I run onboarding support"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["user_email"] == "member@example.com"
    assert body["message"] == "I run onboarding support"

    # Existing admins are notified by email (best-effort, mocked here).
    mock_notify.assert_awaited_once()
    _, kwargs = mock_notify.call_args
    assert kwargs["admin_emails"] == ["admin@example.com"]
    assert kwargs["requester_email"] == "member@example.com"


@patch("routers.admin.send_admin_request_notification", new_callable=AsyncMock)
async def test_duplicate_pending_request_is_idempotent(mock_notify, client, user_factory):
    mock_notify.return_value = True
    await user_factory(email="member@example.com", password="Password123!")
    await _login(client, "member@example.com", "Password123!")

    first = await client.post("/api/admin/requests", json={})
    second = await client.post("/api/admin/requests", json={})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    # Only one notification email should have gone out, not one per call.
    assert mock_notify.await_count == 1


async def test_already_admin_cannot_request_again(client, user_factory):
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    await _login(client, "admin@example.com", "Password123!")

    response = await client.post("/api/admin/requests", json={})
    assert response.status_code == 400


async def test_request_endpoints_require_authentication(client):
    response = await client.post("/api/admin/requests", json={})
    assert response.status_code == 401

    response = await client.get("/api/admin/requests/me")
    assert response.status_code == 401


@patch("routers.admin.send_admin_request_notification", new_callable=AsyncMock)
async def test_non_admin_cannot_list_or_review_requests(mock_notify, client, user_factory):
    mock_notify.return_value = True
    await user_factory(email="member@example.com", password="Password123!")
    await _login(client, "member@example.com", "Password123!")
    await client.post("/api/admin/requests", json={})

    assert (await client.get("/api/admin/requests")).status_code == 403
    assert (await client.post(f"/api/admin/requests/{uuid.uuid4()}/approve")).status_code == 403
    assert (await client.post(f"/api/admin/requests/{uuid.uuid4()}/reject")).status_code == 403


@patch("routers.admin.send_admin_request_decision_email", new_callable=AsyncMock)
@patch("routers.admin.send_admin_request_notification", new_callable=AsyncMock)
async def test_admin_can_approve_request_and_grant_admin_access(mock_notify, mock_decision, client, user_factory):
    mock_notify.return_value = True
    mock_decision.return_value = True
    admin = await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    member = await user_factory(email="member@example.com", password="Password123!")

    await _login(client, "member@example.com", "Password123!")
    created = await client.post("/api/admin/requests", json={})
    request_id = created.json()["id"]

    await _login(client, "admin@example.com", "Password123!")
    pending = await client.get("/api/admin/requests")
    assert pending.status_code == 200
    assert len(pending.json()) == 1
    assert pending.json()[0]["id"] == request_id

    approve = await client.post(f"/api/admin/requests/{request_id}/approve")
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    mock_decision.assert_awaited_once_with(to_email="member@example.com", approved=True)

    # The now-pending list should be empty; member should now be able to
    # reach admin-only endpoints.
    still_pending = await client.get("/api/admin/requests")
    assert still_pending.json() == []

    await _login(client, "member@example.com", "Password123!")
    me_response = await client.get("/api/auth/me")
    assert me_response.json()["is_admin"] is True
    assert (await client.get("/api/admin/metrics/summary")).status_code == 200


@patch("routers.admin.send_admin_request_decision_email", new_callable=AsyncMock)
@patch("routers.admin.send_admin_request_notification", new_callable=AsyncMock)
async def test_admin_can_reject_request_without_granting_access(mock_notify, mock_decision, client, user_factory):
    mock_notify.return_value = True
    mock_decision.return_value = True
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    await user_factory(email="member@example.com", password="Password123!")

    await _login(client, "member@example.com", "Password123!")
    created = await client.post("/api/admin/requests", json={})
    request_id = created.json()["id"]

    await _login(client, "admin@example.com", "Password123!")
    reject = await client.post(f"/api/admin/requests/{request_id}/reject")
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"
    mock_decision.assert_awaited_once_with(to_email="member@example.com", approved=False)

    await _login(client, "member@example.com", "Password123!")
    me_response = await client.get("/api/auth/me")
    assert me_response.json()["is_admin"] is False
    assert (await client.get("/api/admin/metrics/summary")).status_code == 403


@patch("routers.admin.send_admin_request_notification", new_callable=AsyncMock)
async def test_cannot_approve_or_reject_an_already_reviewed_request(mock_notify, client, user_factory):
    mock_notify.return_value = True
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    await user_factory(email="member@example.com", password="Password123!")

    await _login(client, "member@example.com", "Password123!")
    created = await client.post("/api/admin/requests", json={})
    request_id = created.json()["id"]

    await _login(client, "admin@example.com", "Password123!")
    first = await client.post(f"/api/admin/requests/{request_id}/approve")
    assert first.status_code == 200

    second = await client.post(f"/api/admin/requests/{request_id}/approve")
    assert second.status_code == 400

    reject_after_approve = await client.post(f"/api/admin/requests/{request_id}/reject")
    assert reject_after_approve.status_code == 400
