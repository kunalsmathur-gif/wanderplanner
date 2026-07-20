"""Integration tests for cookie-based auth flows and self-service account deletion."""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from core.auth_dependency import ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE
from db_models import RefreshToken, User
from main import app

pytestmark = pytest.mark.asyncio


async def test_signup_requires_consent_field(client):
    response = await client.post(
        "/api/auth/signup",
        json={"email": "missing-consent@example.com", "password": "Password123!"},
    )

    assert response.status_code == 422
    assert "consent_accepted" in response.text


async def test_signup_rejects_false_consent(client):
    response = await client.post(
        "/api/auth/signup",
        json={
            "email": "consent-false@example.com",
            "password": "Password123!",
            "consent_accepted": False,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "You must accept the Terms of Service and Privacy Policy to sign up."


async def test_signup_sets_session_cookies_and_captures_consent_timestamp(client, db_session_maker):
    response = await client.post(
        "/api/auth/signup",
        json={
            "email": "traveler@example.com",
            "password": "Password123!",
            "display_name": "Traveler",
            "consent_accepted": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] == "traveler@example.com"
    assert client.cookies.get(ACCESS_TOKEN_COOKIE)
    assert client.cookies.get(REFRESH_TOKEN_COOKIE)

    me_response = await client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["display_name"] == "Traveler"

    async with db_session_maker() as session:
        user = (await session.execute(select(User).where(User.email == "traveler@example.com"))).scalar_one()
        assert user.consent_accepted_at is not None


async def test_signup_rejects_duplicate_email(client):
    payload = {
        "email": "duplicate@example.com",
        "password": "Password123!",
        "display_name": "Duplicate",
        "consent_accepted": True,
    }

    first = await client.post("/api/auth/signup", json=payload)
    second = await client.post("/api/auth/signup", json=payload)

    assert first.status_code == 200
    assert second.status_code == 400
    # Explicit, actionable message is an intentional product decision — see
    # the comment in routers/auth.py::signup() (trades some account-
    # enumeration resistance for clearer signup UX).
    assert second.json()["detail"] == "An account with this email already exists. Try logging in instead."


async def test_login_rejects_wrong_password_and_unknown_email_with_same_response(client, user_factory):
    await user_factory(email="known@example.com", password="CorrectPassword123!")

    wrong_password = await client.post(
        "/api/auth/login",
        json={"email": "known@example.com", "password": "WrongPassword123!"},
    )
    unknown_email = await client.post(
        "/api/auth/login",
        json={"email": "unknown@example.com", "password": "WrongPassword123!"},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {"detail": "Incorrect email or password."}


async def test_refresh_token_rotation_rejects_reused_token(client, db_session_maker):
    signup = await client.post(
        "/api/auth/signup",
        json={
            "email": "refresh@example.com",
            "password": "Password123!",
            "consent_accepted": True,
        },
    )
    assert signup.status_code == 200

    old_refresh_token = client.cookies.get(REFRESH_TOKEN_COOKIE)
    refresh_response = await client.post("/api/auth/refresh")

    assert refresh_response.status_code == 200
    new_refresh_token = client.cookies.get(REFRESH_TOKEN_COOKIE)
    assert new_refresh_token
    assert new_refresh_token != old_refresh_token

    async with db_session_maker() as session:
        tokens = (await session.execute(select(RefreshToken).order_by(RefreshToken.created_at))).scalars().all()
        assert len(tokens) == 2
        assert sum(token.revoked_at is not None for token in tokens) == 1

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 9999)),
        base_url="http://test",
    ) as replay_client:
        replay_client.cookies.set(REFRESH_TOKEN_COOKIE, old_refresh_token)
        replay_response = await replay_client.post("/api/auth/refresh")

    assert replay_response.status_code == 401
    assert replay_response.json()["detail"] == "Session expired, please sign in again."


async def test_logout_revokes_refresh_token_and_clears_cookies(client, db_session_maker):
    signup = await client.post(
        "/api/auth/signup",
        json={
            "email": "logout@example.com",
            "password": "Password123!",
            "consent_accepted": True,
        },
    )
    assert signup.status_code == 200

    logout_response = await client.post("/api/auth/logout")

    assert logout_response.status_code == 200
    assert logout_response.json() == {"status": "logged_out"}
    assert client.cookies.get(ACCESS_TOKEN_COOKIE) is None
    assert client.cookies.get(REFRESH_TOKEN_COOKIE) is None

    async with db_session_maker() as session:
        token = (
            await session.execute(select(RefreshToken).where(RefreshToken.token_hash.is_not(None)))
        ).scalar_one()
        assert token.revoked_at is not None

    me_response = await client.get("/api/auth/me")
    assert me_response.status_code == 401


async def test_delete_me_removes_user_and_refresh_tokens(client, db_session_maker):
    signup = await client.post(
        "/api/auth/signup",
        json={
            "email": "delete-me@example.com",
            "password": "Password123!",
            "consent_accepted": True,
        },
    )
    assert signup.status_code == 200

    user_id = uuid.UUID(signup.json()["id"])
    access_token = client.cookies.get(ACCESS_TOKEN_COOKIE)

    delete_response = await client.delete("/api/auth/me")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "account_deleted"}

    async with db_session_maker() as session:
        deleted_user = await session.get(User, user_id)
        assert deleted_user is None
        refresh_tokens = (
            await session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id))
        ).scalars().all()
        assert refresh_tokens == []

    me_response = await client.get("/api/auth/me")
    assert me_response.status_code == 401

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 10001)),
        base_url="http://test",
    ) as replay_client:
        replay_client.cookies.set(ACCESS_TOKEN_COOKIE, access_token)
        replay_response = await replay_client.get("/api/auth/me")

    assert replay_response.status_code == 401
