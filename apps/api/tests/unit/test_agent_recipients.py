"""Unit tests for core/agent_recipients.py — who gets notified when a user
requests a quotation (see docs/system-design.md §9B)."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

import core.agent_recipients as agent_recipients_module
from core.agent_recipients import get_quotation_recipient_emails
from db_models import User

pytestmark = pytest.mark.asyncio


async def test_falls_back_to_admin_emails_when_config_file_empty(
    db_session_maker, user_factory, monkeypatch, tmp_path
):
    empty_config = tmp_path / "agent_recipients.json"
    empty_config.write_text(json.dumps({"agent_emails": []}))
    monkeypatch.setattr(agent_recipients_module, "_CONFIG_PATH", empty_config)

    await user_factory(email="admin-one@example.com", password="Password123!", is_admin=True)
    await user_factory(email="admin-two@example.com", password="Password123!", is_admin=True)
    await user_factory(email="not-admin@example.com", password="Password123!", is_admin=False)

    async with db_session_maker() as session:
        emails = await get_quotation_recipient_emails(session)

    assert set(emails) == {"admin-one@example.com", "admin-two@example.com"}


async def test_uses_configured_emails_once_roster_is_populated(
    db_session_maker, user_factory, monkeypatch, tmp_path
):
    populated_config = tmp_path / "agent_recipients.json"
    populated_config.write_text(json.dumps({"agent_emails": ["agent@wanderplanner.org"]}))
    monkeypatch.setattr(agent_recipients_module, "_CONFIG_PATH", populated_config)

    await user_factory(email="admin-one@example.com", password="Password123!", is_admin=True)

    async with db_session_maker() as session:
        emails = await get_quotation_recipient_emails(session)
        # Sanity check: the admin user really exists, but must NOT be used
        # once the config file has entries.
        admins = (await session.execute(select(User).where(User.is_admin.is_(True)))).scalars().all()
        assert len(admins) == 1

    assert emails == ["agent@wanderplanner.org"]


async def test_missing_config_file_falls_back_to_admin_emails(
    db_session_maker, user_factory, monkeypatch, tmp_path
):
    monkeypatch.setattr(agent_recipients_module, "_CONFIG_PATH", tmp_path / "does-not-exist.json")
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)

    async with db_session_maker() as session:
        emails = await get_quotation_recipient_emails(session)

    assert emails == ["admin@example.com"]
