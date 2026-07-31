"""Resolves who gets notified when a user requests a local-expert quotation.

Two modes, controlled entirely by `config/agent_recipients.json`:

- **Sole-builder mode** (default, empty `agent_emails`): every user flagged
  `is_admin = true` gets the quotation-request email. Nothing to configure.
- **Scaled mode**: once `agent_emails` is populated, notifications go to
  exactly those addresses instead — lets a real agent/ops team receive leads
  without every one of them needing an admin account.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import User

_log = logging.getLogger("wanderplanner.agent_recipients")

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "agent_recipients.json"


def _load_configured_emails() -> list[str]:
    try:
        raw = json.loads(_CONFIG_PATH.read_text())
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError):
        _log.warning("Could not read/parse %s — falling back to admin-user emails", _CONFIG_PATH)
        return []

    emails = raw.get("agent_emails") or []
    return [email.strip() for email in emails if isinstance(email, str) and email.strip()]


async def get_quotation_recipient_emails(db: AsyncSession) -> list[str]:
    """Returns the email addresses that should receive a quotation-request
    notification right now — re-reads the config file on every call so
    editing it takes effect without a redeploy."""
    configured = _load_configured_emails()
    if configured:
        return configured

    rows = (
        await db.execute(select(User.email).where(User.is_admin.is_(True), User.email.is_not(None)))
    ).all()
    return [row[0] for row in rows]
