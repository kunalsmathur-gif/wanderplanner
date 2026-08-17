"""Integration tests for cookie-based auth flows and self-service account deletion."""
from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select

from core.auth_dependency import ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE
from core.config import settings
from db_models import RefreshToken, User
from main import app

pytestmark = pytest.mark.asyncio


class _StubGoogleClient:
    """Stands in for `httpx.AsyncClient` inside `google_callback`.

    respx (the usual httpx-mocking lib, pinned in requirements-dev.txt) is
    incompatible with the installed httpx 0.28.1 — its patched transport
    never matches, failing every request with `AllMockedAssertionError` even
    for a bare respx smoke test outside this suite. Monkeypatching the
    `httpx.AsyncClient` constructor directly sidesteps that mismatch without
    touching the (unrelated) pinned dependency version.
    """

    def __init__(self, *, token_response: Response, userinfo_response: Response):
        self._token_response = token_response
        self._userinfo_response = userinfo_response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, **kwargs):
        assert url == "https://oauth2.googleapis.com/token"
        return self._token_response

    async def get(self, url, **kwargs):
        assert url == "https://openidconnect.googleapis.com/v1/userinfo"
        return self._userinfo_response


def _mock_google_client(monkeypatch, *, token_response: Response, userinfo_response: Response):
    monkeypatch.setattr(
        "routers.auth.httpx.AsyncClient",
        lambda *args, **kwargs: _StubGoogleClient(token_response=token_response, userinfo_response=userinfo_response),
    )


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


# --- Google SSO -------------------------------------------------------------
# `_test_safe_settings` (conftest, autouse) blanks google_client_id/secret by
# default so every other test in this module runs with SSO "not configured".
# These tests explicitly monkeypatch a fake client id/secret back in.


async def test_auth_config_reports_google_sso_disabled_by_default(client):
    response = await client.get("/api/auth/config")

    assert response.status_code == 200
    assert response.json() == {"google_sso_enabled": False}


async def test_auth_config_reports_google_sso_enabled_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "fake-client-id")

    response = await client.get("/api/auth/config")

    assert response.json() == {"google_sso_enabled": True}


async def test_google_start_rejects_when_not_configured(client):
    response = await client.get("/api/auth/google/start", follow_redirects=False)

    assert response.status_code == 503


async def test_google_start_redirects_to_google_with_signed_state(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "fake-client-id")

    response = await client.get(
        "/api/auth/google/start?return_to=/trips/42",
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=fake-client-id" in location
    assert "scope=openid+email+profile" in location
    # The state param carries the return_to signed via itsdangerous, not the
    # raw value — just assert it's present and non-empty.
    assert "state=" in location


async def test_google_callback_rejects_missing_code_or_state(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "fake-secret")

    response = await client.get("/api/auth/google/callback", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == f"{settings.frontend_base_url}/login?error=google_sso_failed"


async def test_google_callback_rejects_tampered_state(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "fake-secret")

    response = await client.get(
        "/api/auth/google/callback?code=some-code&state=not-a-real-signed-state",
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    assert response.headers["location"] == f"{settings.frontend_base_url}/login?error=google_sso_failed"


def _signed_state(return_to: str = "/") -> str:
    from routers.auth import _state_serializer

    return _state_serializer.dumps({"return_to": return_to})


async def test_google_callback_creates_new_user_on_first_sign_in(client, db_session_maker, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "fake-secret")
    state = _signed_state("/trips/new")

    _mock_google_client(
        monkeypatch,
        token_response=Response(200, json={"access_token": "fake-google-access-token"}, request=httpx.Request("POST", "https://oauth2.googleapis.com/token")),
        userinfo_response=Response(
            200,
            json={"sub": "google-sub-123", "email": "newgoogleuser@example.com", "name": "New Googler"},
            request=httpx.Request("GET", "https://openidconnect.googleapis.com/v1/userinfo"),
        ),
    )

    response = await client.get(
        f"/api/auth/google/callback?code=auth-code&state={state}",
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    assert response.headers["location"] == f"{settings.frontend_base_url}/trips/new"
    assert client.cookies.get(ACCESS_TOKEN_COOKIE)
    assert client.cookies.get(REFRESH_TOKEN_COOKIE)

    async with db_session_maker() as session:
        user = (
            await session.execute(select(User).where(User.google_sub == "google-sub-123"))
        ).scalar_one()
        assert user.email == "newgoogleuser@example.com"
        assert user.display_name == "New Googler"
        assert user.password_hash is None


async def test_google_callback_links_existing_password_account_by_email(client, db_session_maker, user_factory, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "fake-secret")
    existing_user = await user_factory(email="already-signed-up@example.com")
    state = _signed_state("/")

    _mock_google_client(
        monkeypatch,
        token_response=Response(200, json={"access_token": "fake-google-access-token"}, request=httpx.Request("POST", "https://oauth2.googleapis.com/token")),
        userinfo_response=Response(
            200,
            json={"sub": "google-sub-456", "email": "already-signed-up@example.com", "name": "Existing User"},
            request=httpx.Request("GET", "https://openidconnect.googleapis.com/v1/userinfo"),
        ),
    )

    response = await client.get(
        f"/api/auth/google/callback?code=auth-code&state={state}",
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    assert response.headers["location"] == f"{settings.frontend_base_url}/"

    async with db_session_maker() as session:
        linked_user = await session.get(User, existing_user.id)
        assert linked_user.google_sub == "google-sub-456"
        # Original password hash is preserved — linking, not replacing.
        assert linked_user.password_hash is not None


async def test_google_callback_redirects_to_login_error_on_token_exchange_failure(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "fake-secret")
    state = _signed_state("/")

    _mock_google_client(
        monkeypatch,
        token_response=Response(400, json={"error": "invalid_grant"}, request=httpx.Request("POST", "https://oauth2.googleapis.com/token")),
        userinfo_response=Response(200, json={}, request=httpx.Request("GET", "https://openidconnect.googleapis.com/v1/userinfo")),
    )

    response = await client.get(
        f"/api/auth/google/callback?code=bad-code&state={state}",
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    assert response.headers["location"] == f"{settings.frontend_base_url}/login?error=google_sso_failed"
