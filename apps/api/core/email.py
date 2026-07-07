"""Transactional email via Resend's HTTP API (no SDK dependency needed —
a single POST call keeps this consistent with the rest of the codebase's
httpx-based external API clients, e.g. services/pexels.py).
"""
from __future__ import annotations

import logging

import httpx

from core.config import settings

_log = logging.getLogger("wanderplanner.email")

_RESEND_URL = "https://api.resend.com/emails"


async def send_password_reset_email(*, to_email: str, reset_url: str) -> bool:
    """Best-effort send — returns False on failure rather than raising, so a
    transient email-provider outage never surfaces as a 500 to the user
    (the /auth/password/forgot endpoint always returns a generic success
    response regardless, to avoid account enumeration)."""
    if not settings.resend_api_key:
        # Local/dev convenience only — this branch is never reached in prod
        # since RESEND_API_KEY is always configured there. Logging the raw
        # link here (instead of just a warning) lets developers exercise the
        # reset flow end-to-end without a real email provider.
        _log.warning(
            "RESEND_API_KEY not configured — password reset email not sent. "
            "Local dev reset link for %s: %s",
            to_email,
            reset_url,
        )
        return False

    html = f"""
    <p>We received a request to reset your Wanderplanner password.</p>
    <p><a href="{reset_url}">Click here to choose a new password</a> (link expires in
    {settings.password_reset_token_ttl_minutes} minutes).</p>
    <p>If you didn't request this, you can safely ignore this email.</p>
    """

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _RESEND_URL,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.email_from_address,
                    "to": [to_email],
                    "subject": "Reset your Wanderplanner password",
                    "html": html,
                },
            )
            resp.raise_for_status()
            return True
    except httpx.HTTPError:
        _log.exception("Failed to send password reset email")
        return False
