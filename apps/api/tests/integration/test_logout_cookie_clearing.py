"""Does logout actually clear the session cookies in a production-shaped
deployment? (Reported live: after logging out, returning to the site shows the
user still signed in.)

The revocation half is already covered in test_auth.py — this is specifically
about the `Set-Cookie` *attributes* on the way out, which is what decides
whether the browser drops the cookie or silently ignores the header.
"""
from __future__ import annotations

import pytest

from core.auth_dependency import ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE

pytestmark = pytest.mark.asyncio


def _cookie_headers(response, name: str) -> str:
    """The raw Set-Cookie line for `name` (httpx lowercases header names)."""
    for key, value in response.headers.multi_items():
        if key.lower() == "set-cookie" and value.startswith(f"{name}="):
            return value
    return ""


async def _production_cookies(monkeypatch) -> None:
    """The live deployment's cookie configuration: HTTPS, cross-site-capable."""
    from core.config import settings

    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(settings, "cookie_samesite", "none")


async def test_logout_clears_cookies_with_the_same_attributes_they_were_set_with(
    client, monkeypatch
):
    """A Set-Cookie that drops `Secure` while the original had it cannot
    remove that cookie over HTTPS, and `SameSite=none` -> `lax` narrows the
    context the header is honoured in. The deletion has to mirror the
    issuance or the browser keeps the cookie — and the access token stays
    valid for its full TTL, so the user stays signed in.
    """
    await _production_cookies(monkeypatch)

    await client.post(
        "/api/auth/signup",
        json={
            "email": "logout-cookies@example.com",
            "password": "Password123!",
            "consent_accepted": True,
        },
    )

    login = await client.post(
        "/api/auth/login",
        json={"email": "logout-cookies@example.com", "password": "Password123!"},
    )
    assert login.status_code == 200
    set_access = _cookie_headers(login, ACCESS_TOKEN_COOKIE)
    assert "secure" in set_access.lower()
    assert "samesite=none" in set_access.lower()

    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 200

    for name in (ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE):
        cleared = _cookie_headers(logout, name)
        assert cleared, f"logout sent no Set-Cookie for {name}"
        lowered = cleared.lower()
        assert "secure" in lowered, (
            f"{name} deletion dropped Secure; a non-Secure Set-Cookie cannot "
            f"clear a Secure cookie: {cleared}"
        )
        assert "samesite=none" in lowered, (
            f"{name} deletion narrowed SameSite from none to lax, so the header "
            f"is ignored in the cross-site context the cookie was made for: {cleared}"
        )
        assert "httponly" in lowered, f"{name} deletion dropped HttpOnly: {cleared}"


async def test_access_token_is_rejected_after_logout(client):
    """The end-to-end symptom: /auth/me must not keep answering 200 with the
    same cookie jar once the user has logged out."""
    await client.post(
        "/api/auth/signup",
        json={
            "email": "logout-me@example.com",
            "password": "Password123!",
            "consent_accepted": True,
        },
    )
    assert (await client.get("/api/auth/me")).status_code == 200

    await client.post("/api/auth/logout")

    assert (await client.get("/api/auth/me")).status_code == 401
