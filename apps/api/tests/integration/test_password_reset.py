"""Integration tests for forgot-password and password reset token flows."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from core.security import generate_password_reset_token
from db_models import PasswordResetToken

pytestmark = pytest.mark.asyncio


async def test_forgot_password_returns_same_response_for_existing_and_unknown_email(
    client,
    db_session_maker,
    user_factory,
):
    user = await user_factory(email="forgot@example.com")

    existing_response = await client.post(
        "/api/auth/password/forgot",
        json={"email": "forgot@example.com"},
    )
    missing_response = await client.post(
        "/api/auth/password/forgot",
        json={"email": "missing@example.com"},
    )

    assert existing_response.status_code == missing_response.status_code == 200
    assert existing_response.json() == missing_response.json() == {"status": "if_account_exists_email_sent"}

    async with db_session_maker() as session:
        tokens = (
            await session.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
        ).scalars().all()
        assert len(tokens) == 1


async def test_reset_password_accepts_valid_token_once_and_updates_credentials(
    client,
    db_session_maker,
    user_factory,
):
    user = await user_factory(email="reset@example.com", password="OldPassword123!")
    raw_token, token_hash, expires_at = generate_password_reset_token()

    async with db_session_maker() as session:
        session.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
        await session.commit()

    reset_response = await client.post(
        "/api/auth/password/reset",
        json={"token": raw_token, "new_password": "NewPassword123!"},
    )
    reuse_response = await client.post(
        "/api/auth/password/reset",
        json={"token": raw_token, "new_password": "AnotherPassword123!"},
    )

    assert reset_response.status_code == 200
    assert reset_response.json() == {"status": "password_updated"}
    assert reuse_response.status_code == 400
    assert reuse_response.json()["detail"] == "This password reset link is invalid or has expired."

    old_login = await client.post(
        "/api/auth/login",
        json={"email": "reset@example.com", "password": "OldPassword123!"},
    )
    new_login = await client.post(
        "/api/auth/login",
        json={"email": "reset@example.com", "password": "NewPassword123!"},
    )

    assert old_login.status_code == 401
    assert new_login.status_code == 200

    async with db_session_maker() as session:
        stored = (
            await session.execute(
                select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
            )
        ).scalar_one()
        assert stored.used_at is not None


async def test_reset_password_rejects_expired_token(client, db_session_maker, user_factory):
    user = await user_factory(email="expired@example.com")
    raw_token, token_hash, _ = generate_password_reset_token()

    async with db_session_maker() as session:
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            )
        )
        await session.commit()

    response = await client.post(
        "/api/auth/password/reset",
        json={"token": raw_token, "new_password": "NewPassword123!"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "This password reset link is invalid or has expired."


async def test_reset_password_rejects_garbage_token(client):
    response = await client.post(
        "/api/auth/password/reset",
        json={"token": "not-a-real-token", "new_password": "NewPassword123!"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "This password reset link is invalid or has expired."
