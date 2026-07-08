"""Signup / login / Google SSO / session refresh & logout.

Session model: short-lived JWT access token (~15 min) in an httpOnly cookie,
plus a longer-lived opaque refresh token (also httpOnly cookie) whose SHA-256
hash is stored in `refresh_tokens` — rotated on every /auth/refresh call.

Google SSO uses a manual Authorization Code flow (no server-side session
middleware needed): the `state` param is a signed, short-lived token via
`itsdangerous` rather than a server-stored session, so no session store is
required and the flow works fine behind a load balancer.
"""
import logging
from typing import Optional
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.analytics import log_event
from core.auth_dependency import ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE, get_current_user
from core.config import settings
from core.email import send_password_reset_email
from core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from core.security import (
    create_access_token,
    generate_password_reset_token,
    generate_refresh_token,
    hash_ip,
    hash_password,
    hash_refresh_token,
    hash_reset_token,
    verify_password,
)
from db import get_db
from db_models import PasswordResetToken, RefreshToken, User
from models.auth import ForgotPasswordRequest, LoginRequest, ResetPasswordRequest, SignupRequest, UserResponse

router = APIRouter()
_log = logging.getLogger("wanderplanner.auth")

_state_serializer = URLSafeTimedSerializer(settings.jwt_secret, salt="google-oauth-state")

AUTH_RATE_LIMIT = "10/minute"  # brute-force/signup-spam protection


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        auth_provider="google" if user.google_sub else "password",
    )


async def _issue_session(response: Response, db: AsyncSession, user: User, request: Request) -> None:
    """Set access + refresh cookies and persist the new refresh token."""
    access_token = create_access_token(user.id)
    raw_refresh, refresh_hash, expires_at = generate_refresh_token()

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=expires_at,
            user_agent=(request.headers.get("user-agent") or "")[:255],
            ip_hash=hash_ip(request.client.host if request.client else None),
        )
    )
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    cookie_kwargs = dict(
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain or None,
        path="/",
    )
    response.set_cookie(ACCESS_TOKEN_COOKIE, access_token, max_age=settings.access_token_ttl_minutes * 60, **cookie_kwargs)
    response.set_cookie(REFRESH_TOKEN_COOKIE, raw_refresh, max_age=settings.refresh_token_ttl_days * 86400, **cookie_kwargs)


def _clear_session_cookies(response: Response) -> None:
    for name in (ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE):
        response.delete_cookie(name, domain=settings.cookie_domain or None, path="/")


@router.post("/auth/signup", response_model=UserResponse)
@limiter.limit(AUTH_RATE_LIMIT)
async def signup(request: Request, response: Response, body: SignupRequest, db: AsyncSession = Depends(get_db)) -> UserResponse:
    if not body.consent_accepted:
        raise HTTPException(status_code=400, detail="You must accept the Terms of Service and Privacy Policy to sign up.")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        # Same generic message whether or not the email exists, to avoid
        # account enumeration.
        raise HTTPException(status_code=400, detail="Unable to sign up with these details.")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        consent_accepted_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()

    await _issue_session(response, db, user, request)
    await log_event(db, "signup", user_id=user.id, metadata={"provider": "password"})

    return _user_response(user)


@router.post("/auth/login", response_model=UserResponse)
@limiter.limit(AUTH_RATE_LIMIT)
async def login(request: Request, response: Response, body: LoginRequest, db: AsyncSession = Depends(get_db)) -> UserResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        await log_event(db, "login_failed", metadata={"email_domain": body.email.split("@")[-1]})
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account has been disabled.")

    await _issue_session(response, db, user, request)
    await log_event(db, "login_success", user_id=user.id, metadata={"provider": "password"})

    return _user_response(user)


@router.get("/auth/google/start")
@limiter.limit(DEFAULT_RATE_LIMIT)
async def google_start(request: Request, return_to: str = "/") -> Response:
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")

    state = _state_serializer.dumps({"return_to": return_to})
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    from fastapi.responses import RedirectResponse

    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


@router.get("/auth/google/callback")
@limiter.limit(DEFAULT_RATE_LIMIT)
async def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> Response:
    from fastapi.responses import RedirectResponse

    frontend_error_url = f"{settings.frontend_base_url}/login?error=google_sso_failed"

    if error or not code or not state:
        return RedirectResponse(frontend_error_url)

    try:
        state_data = _state_serializer.loads(state, max_age=600)
    except (BadSignature, SignatureExpired):
        return RedirectResponse(frontend_error_url)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            userinfo_resp = await client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_resp.raise_for_status()
            info = userinfo_resp.json()
    except (httpx.HTTPError, KeyError):
        _log.exception("Google OAuth exchange failed")
        return RedirectResponse(frontend_error_url)

    google_sub = info.get("sub")
    email = info.get("email")
    if not google_sub:
        return RedirectResponse(frontend_error_url)

    result = await db.execute(select(User).where(User.google_sub == google_sub))
    user = result.scalar_one_or_none()

    if user is None and email:
        # Link to an existing password account with the same verified email,
        # rather than creating a duplicate.
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            google_sub=google_sub,
            display_name=info.get("name"),
            consent_accepted_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()
        event_type = "signup"
    else:
        if not user.google_sub:
            user.google_sub = google_sub
        event_type = "login_success"

    redirect = RedirectResponse(f"{settings.frontend_base_url}{state_data.get('return_to', '/')}")
    await _issue_session(redirect, db, user, request)
    await log_event(db, event_type, user_id=user.id, metadata={"provider": "google"})

    return redirect


@router.post("/auth/refresh", response_model=UserResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    raw_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=401, detail="No active session.")

    token_hash = hash_refresh_token(raw_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    expires_at = stored.expires_at if stored else None
    if expires_at is not None and expires_at.tzinfo is None:
        # Defensive: some DB backends (e.g. SQLite in local/dev) don't
        # round-trip tz-aware datetimes — assume UTC rather than crash.
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if stored is None or stored.revoked_at is not None or expires_at < now:
        _clear_session_cookies(response)
        raise HTTPException(status_code=401, detail="Session expired, please sign in again.")

    user = await db.get(User, stored.user_id)
    if user is None or not user.is_active:
        _clear_session_cookies(response)
        raise HTTPException(status_code=401, detail="Account not found or disabled.")

    # Rotate: revoke the old refresh token, issue a brand new pair.
    stored.revoked_at = now
    await _issue_session(response, db, user, request)

    return _user_response(user)


@router.post("/auth/logout")
@limiter.limit(DEFAULT_RATE_LIMIT)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    raw_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if raw_token:
        token_hash = hash_refresh_token(raw_token)
        result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        stored = result.scalar_one_or_none()
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = datetime.now(timezone.utc)
            await db.commit()

    _clear_session_cookies(response)
    return {"status": "logged_out"}


@router.get("/auth/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return _user_response(user)


@router.delete("/auth/me")
@limiter.limit(AUTH_RATE_LIMIT)
async def delete_my_account(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Self-service right-to-erasure: deletes the account outright.

    refresh_tokens cascade-delete (FK ondelete=CASCADE); events.user_id is
    set to NULL (FK ondelete=SET NULL) so aggregate analytics survive without
    retaining any PII. Logged as a metadata-only event *before* the row is
    gone, since the FK would otherwise null it out immediately.
    """
    await log_event(db, "account_deleted", user_id=user.id, metadata={"self_service": True})

    await db.delete(user)
    await db.commit()

    _clear_session_cookies(response)
    return {"status": "account_deleted"}


@router.post("/auth/password/forgot")
@limiter.limit(AUTH_RATE_LIMIT)
async def forgot_password(request: Request, body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Always returns a generic response, whether or not the email exists —
    this prevents account enumeration via response-timing/content."""
    generic_response = {"status": "if_account_exists_email_sent"}

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Only password accounts can reset via email (Google-only accounts have
    # no password_hash to reset).
    if user is not None and user.is_active:
        raw_token, token_hash, expires_at = generate_password_reset_token()
        db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
        await db.commit()

        reset_url = f"{settings.frontend_base_url}/reset-password?token={raw_token}"
        await send_password_reset_email(to_email=user.email, reset_url=reset_url)
        await log_event(db, "password_reset_requested", user_id=user.id)

    return generic_response


@router.post("/auth/password/reset")
@limiter.limit(AUTH_RATE_LIMIT)
async def reset_password(request: Request, response: Response, body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict:
    token_hash = hash_reset_token(body.token)
    result = await db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    expires_at = stored.expires_at if stored else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if stored is None or stored.used_at is not None or expires_at < now:
        raise HTTPException(status_code=400, detail="This password reset link is invalid or has expired.")

    user = await db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="This password reset link is invalid or has expired.")

    user.password_hash = hash_password(body.new_password)
    stored.used_at = now

    # Changing the password invalidates every existing session — a
    # reasonable defensive measure in case the account was compromised.
    await db.execute(
        RefreshToken.__table__.update()
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.commit()

    _clear_session_cookies(response)
    await log_event(db, "password_reset_completed", user_id=user.id)

    return {"status": "password_updated"}
