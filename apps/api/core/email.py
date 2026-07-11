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


async def send_admin_request_notification(*, admin_emails: list[str], requester_email: str, requester_name: str | None, admin_console_url: str) -> bool:
    """Best-effort notification to every existing admin when a user requests
    admin access. Never blocks/raises the request-creation endpoint on
    failure — the request is still visible in the admin console's Admin
    Requests panel regardless of whether this email send succeeds."""
    if not admin_emails:
        return False

    if not settings.resend_api_key:
        _log.warning(
            "RESEND_API_KEY not configured — admin-request notification not sent. "
            "Would have notified %s about a request from %s",
            admin_emails,
            requester_email,
        )
        return False

    who = requester_name or requester_email
    html = f"""
    <p><strong>{who}</strong> ({requester_email}) has requested admin access to Wanderplanner.</p>
    <p><a href="{admin_console_url}">Review this request in the admin console</a>.</p>
    <p>No one gains admin access automatically — this request stays pending until an existing admin explicitly approves or rejects it.</p>
    """

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _RESEND_URL,
                headers={"Authorization": f"******"},
                json={
                    "from": settings.email_from_address,
                    "to": admin_emails,
                    "subject": f"Admin access requested by {requester_email}",
                    "html": html,
                },
            )
            resp.raise_for_status()
            return True
    except httpx.HTTPError:
        _log.exception("Failed to send admin-request notification email")
        return False


async def send_admin_request_decision_email(*, to_email: str, approved: bool) -> bool:
    """Best-effort notification to the requester once their admin-access
    request has been reviewed."""
    if not settings.resend_api_key:
        _log.warning(
            "RESEND_API_KEY not configured — admin-request decision email not sent to %s (approved=%s)",
            to_email,
            approved,
        )
        return False

    if approved:
        html = "<p>Your request for admin access to Wanderplanner has been <strong>approved</strong>. You now have access to the admin console.</p>"
        subject = "Your admin access request was approved"
    else:
        html = "<p>Your request for admin access to Wanderplanner was <strong>not approved</strong> at this time.</p>"
        subject = "Your admin access request was declined"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _RESEND_URL,
                headers={"Authorization": f"******"},
                json={
                    "from": settings.email_from_address,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
            )
            resp.raise_for_status()
            return True
    except httpx.HTTPError:
        _log.exception("Failed to send admin-request decision email")
        return False
