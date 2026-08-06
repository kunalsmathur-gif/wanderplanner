"""Transactional email via Resend's HTTP API (no SDK dependency needed —
a single POST call keeps this consistent with the rest of the codebase's
httpx-based external API clients, e.g. services/pexels.py).
"""
from __future__ import annotations

import base64
import json
import logging
from html import escape

import httpx

from core.config import settings

_log = logging.getLogger("wanderplanner.email")

_RESEND_URL = "https://api.resend.com/emails"


async def _send_resend_email(
    *,
    to: list[str],
    subject: str,
    html: str,
    attachments: list[dict[str, str]] | None = None,
) -> bool:
    """`attachments` (optional) is Resend's own shape: a list of
    `{"filename": ..., "content": <base64-encoded bytes, no data: prefix>}`."""
    try:
        # Annotated because the values are heterogeneous: without it the
        # literal infers as dict[str, Sequence[str]] (a bare `str` satisfies
        # Sequence[str]) and the attachment list below no longer fits.
        payload: dict[str, object] = {
            "from": settings.email_from_address,
            "to": to,
            "subject": subject,
            "html": html,
        }
        if attachments:
            payload["attachments"] = attachments

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _RESEND_URL,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            return True
    except httpx.HTTPError:
        _log.exception("Failed to send email with subject %s", subject)
        return False


async def send_password_reset_email(*, to_email: str, reset_url: str) -> bool:
    """Best-effort send — returns False on failure rather than raising, so a
    transient email-provider outage never surfaces as a 500 to the user
    (the /auth/password/forgot endpoint always returns a generic success
    response regardless, to avoid account enumeration)."""
    if not settings.resend_api_key:
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

    ok = await _send_resend_email(
        to=[to_email],
        subject="Reset your Wanderplanner password",
        html=html,
    )
    return ok


async def send_admin_request_notification(
    *,
    admin_emails: list[str],
    requester_email: str,
    requester_name: str | None,
    admin_console_url: str,
) -> bool:
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

    ok = await _send_resend_email(
        to=admin_emails,
        subject=f"Admin access requested by {requester_email}",
        html=html,
    )
    return ok


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

    ok = await _send_resend_email(to=[to_email], subject=subject, html=html)
    return ok


async def send_agent_lead_confirmation_email(
    *,
    to_email: str,
    destination: str,
    trip_config_summary: dict,
) -> bool:
    if not settings.resend_api_key:
        _log.warning(
            "RESEND_API_KEY not configured — agent-lead confirmation not sent to %s for %s",
            to_email,
            destination,
        )
        return False

    html = f"""
    <p>Thanks for asking a local expert to help book your Wanderplanner itinerary for <strong>{destination}</strong>.</p>
    <p>We reply within <strong>24 hours, guaranteed</strong>. A destination specialist will review your plan personally — no bots, no generic replies.</p>
    <p>Trip details received:</p>
    <pre>{trip_config_summary}</pre>
    """
    ok = await _send_resend_email(
        to=[to_email],
        subject="Your Wanderplanner local-expert request is in — reply within 24 hours",
        html=html,
    )
    return ok


async def send_agent_lead_request_email(
    *,
    to_emails: list[str],
    lead_id: str,
    lead_email: str,
    destination: str,
    source: str,
    trip_config_summary: dict,
    custom_notes: str | None,
    itinerary_html: str | None,
    pdf_attachment: bytes | None = None,
    pdf_filename: str = "itinerary.pdf",
) -> bool:
    """Fires the moment a user requests a quotation — this is the actual
    "quote request" notification (as opposed to `send_agent_lead_escalation_email`,
    which only fires if 24h pass with no response). Recipients come from
    `core.agent_recipients.get_quotation_recipient_emails` — every admin in
    sole-builder mode, or the configured agent roster once one exists."""
    if not to_emails:
        return False

    if not settings.resend_api_key:
        _log.warning(
            "RESEND_API_KEY not configured — quotation-request email not sent for lead %s",
            lead_id,
        )
        return False

    notes_html = (
        f"<p><strong>Traveler's notes:</strong><br>{escape(custom_notes)}</p>"
        if custom_notes
        else ""
    )
    itinerary_section = (
        f"<h3>AI-generated itinerary</h3>{itinerary_html}"
        if itinerary_html
        else "<p><em>No itinerary preview was attached — see the PDF, if attached, for the full plan.</em></p>"
    )
    # Surfaces which flow the lead came from at a glance in the inbox — an
    # "infeasible_budget" lead has no itinerary attached by definition (the
    # feasibility gate blocked generation before one existed), so callers
    # shouldn't be surprised by the empty itinerary_section above.
    source_label = (
        "⚠️ Budget infeasible — no itinerary generated"
        if source == "infeasible_budget"
        else "Post-itinerary quotation request"
    )

    html = f"""
    <p><strong>New quotation request — {escape(destination)}</strong></p>
    <p><strong>Source:</strong> {escape(source_label)}</p>
    <p>Reply to the traveler at: <a href="mailto:{escape(lead_email)}">{escape(lead_email)}</a></p>
    <p>Reply within 24 hours to stay inside the promised SLA.</p>
    {notes_html}
    <h3>Trip inputs</h3>
    <pre>{escape(json.dumps(trip_config_summary, indent=2, default=str))}</pre>
    {itinerary_section}
    """

    attachments = None
    if pdf_attachment:
        attachments = [{
            "filename": pdf_filename,
            "content": base64.b64encode(pdf_attachment).decode("ascii"),
        }]

    ok = await _send_resend_email(
        to=to_emails,
        subject=f"New quotation request — {destination}"
        + (" [Budget infeasible]" if source == "infeasible_budget" else ""),
        html=html,
        attachments=attachments,
    )
    return ok


async def send_agent_lead_escalation_email(
    *,
    admin_emails: list[str],
    lead_id: str,
    destination: str,
    lead_email: str,
) -> bool:
    if not admin_emails:
        return False

    if not settings.resend_api_key:
        _log.warning(
            "RESEND_API_KEY not configured — agent-lead escalation not sent for %s",
            lead_id,
        )
        return False

    html = f"""
    <p><strong>UNANSWERED LEAD — respond now.</strong></p>
    <p>Lead <strong>{lead_id}</strong> for <strong>{destination}</strong> has gone unanswered for 24 hours.</p>
    <p>Reply to: {lead_email}</p>
    """
    ok = await _send_resend_email(
        to=admin_emails,
        subject="UNANSWERED LEAD — respond now",
        html=html,
    )
    return ok


async def send_agent_lead_reassurance_email(*, to_email: str, destination: str) -> bool:
    if not settings.resend_api_key:
        _log.warning(
            "RESEND_API_KEY not configured — agent-lead reassurance not sent to %s for %s",
            to_email,
            destination,
        )
        return False

    html = f"""
    <p>Thanks for your patience on your <strong>{destination}</strong> itinerary request.</p>
    <p>We're seeing higher demand than expected, but a destination specialist will reach out within <strong>24 more hours</strong>.</p>
    """
    ok = await _send_resend_email(
        to=[to_email],
        subject="Update on your Wanderplanner local-expert request",
        html=html,
    )
    return ok
