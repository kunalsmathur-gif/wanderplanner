from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from core.scheduler import _check_agent_lead_sla
from db_models import AgentLead

pytestmark = pytest.mark.asyncio


async def _create_lead(
    db_session_maker,
    *,
    email: str = "traveler@example.com",
    destination: str = "Kyoto",
    created_at: datetime,
    responded_at: datetime | None = None,
    escalated_at: datetime | None = None,
    reassurance_sent_at: datetime | None = None,
):
    async with db_session_maker() as session:
        lead = AgentLead(
            email=email,
            destination=destination,
            trip_config_summary={"pax": 2},
            created_at=created_at,
            responded_at=responded_at,
            escalated_at=escalated_at,
            reassurance_sent_at=reassurance_sent_at,
        )
        session.add(lead)
        await session.commit()
        await session.refresh(lead)
        return lead


@pytest.fixture
def _override_scheduler_db(monkeypatch: pytest.MonkeyPatch, db_session_maker):
    import db as db_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", db_session_maker)


@patch("core.email.send_agent_lead_reassurance_email", new_callable=AsyncMock)
@patch("core.email.send_agent_lead_escalation_email", new_callable=AsyncMock)
async def test_not_yet_due_lead_sends_no_emails(
    mock_escalate,
    mock_reassure,
    db_session_maker,
    user_factory,
    _override_scheduler_db,
):
    now = datetime.now(UTC)
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    await _create_lead(db_session_maker, created_at=now - timedelta(hours=23))

    await _check_agent_lead_sla(now=now)

    mock_escalate.assert_not_awaited()
    mock_reassure.assert_not_awaited()


@patch("core.email.send_agent_lead_reassurance_email", new_callable=AsyncMock)
@patch("core.email.send_agent_lead_escalation_email", new_callable=AsyncMock)
async def test_due_lead_escalates_once(
    mock_escalate,
    mock_reassure,
    db_session_maker,
    user_factory,
    _override_scheduler_db,
):
    now = datetime.now(UTC)
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    lead = await _create_lead(db_session_maker, created_at=now - timedelta(hours=25))

    await _check_agent_lead_sla(now=now)
    await _check_agent_lead_sla(now=now + timedelta(minutes=5))

    mock_escalate.assert_awaited_once()
    mock_reassure.assert_not_awaited()

    async with db_session_maker() as session:
        refreshed = (await session.execute(select(AgentLead).where(AgentLead.id == lead.id))).scalar_one()
        assert refreshed.escalated_at == now.replace(tzinfo=None)


@patch("core.email.send_agent_lead_reassurance_email", new_callable=AsyncMock)
@patch("core.email.send_agent_lead_escalation_email", new_callable=AsyncMock)
async def test_already_escalated_lead_does_not_duplicate(
    mock_escalate,
    mock_reassure,
    db_session_maker,
    user_factory,
    _override_scheduler_db,
):
    now = datetime.now(UTC)
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    await _create_lead(
        db_session_maker,
        created_at=now - timedelta(hours=25),
        escalated_at=now - timedelta(minutes=1),
    )

    await _check_agent_lead_sla(now=now)

    mock_escalate.assert_not_awaited()
    mock_reassure.assert_not_awaited()


@patch("core.email.send_agent_lead_reassurance_email", new_callable=AsyncMock)
@patch("core.email.send_agent_lead_escalation_email", new_callable=AsyncMock)
async def test_responded_lead_short_circuits_threshold_emails(
    mock_escalate,
    mock_reassure,
    db_session_maker,
    user_factory,
    _override_scheduler_db,
):
    now = datetime.now(UTC)
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    await _create_lead(
        db_session_maker,
        created_at=now - timedelta(hours=49),
        responded_at=now - timedelta(hours=2),
    )

    await _check_agent_lead_sla(now=now)

    mock_escalate.assert_not_awaited()
    mock_reassure.assert_not_awaited()


@patch("core.email.send_agent_lead_reassurance_email", new_callable=AsyncMock)
@patch("core.email.send_agent_lead_escalation_email", new_callable=AsyncMock)
async def test_due_lead_sends_reassurance_once(
    mock_escalate,
    mock_reassure,
    db_session_maker,
    user_factory,
    _override_scheduler_db,
):
    now = datetime.now(UTC)
    await user_factory(email="admin@example.com", password="Password123!", is_admin=True)
    lead = await _create_lead(
        db_session_maker,
        created_at=now - timedelta(hours=49),
        escalated_at=now - timedelta(hours=24),
    )

    await _check_agent_lead_sla(now=now)
    await _check_agent_lead_sla(now=now + timedelta(minutes=5))

    mock_escalate.assert_not_awaited()
    mock_reassure.assert_awaited_once()

    async with db_session_maker() as session:
        refreshed = (await session.execute(select(AgentLead).where(AgentLead.id == lead.id))).scalar_one()
        assert refreshed.reassurance_sent_at == now.replace(tzinfo=None)
