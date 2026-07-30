from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from db_models import AgentLead

pytestmark = pytest.mark.asyncio


async def _login(client, email: str, password: str) -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


@patch("routers.agent_leads.send_agent_lead_confirmation_email", new_callable=AsyncMock)
async def test_create_agent_lead_persists_row_and_attempts_confirmation_email(
    mock_send_email,
    client,
    db_session_maker,
    user_factory,
):
    mock_send_email.return_value = True
    user = await user_factory(email="traveler@example.com", password="Password123!")
    await _login(client, "traveler@example.com", "Password123!")

    payload = {
        "email": "traveler@example.com",
        "destination": "Kyoto",
        "trip_config_summary": {
            "dates": {"start": "2026-09-01", "end": "2026-09-07"},
            "pax": 2,
            "budget_tier": "mid-range",
        },
    }

    response = await client.post("/api/agent-leads", json=payload)

    assert response.status_code == 200
    lead_id = uuid.UUID(response.json()["id"])
    assert lead_id

    async with db_session_maker() as session:
        lead = (await session.execute(select(AgentLead).where(AgentLead.id == lead_id))).scalar_one()
        assert str(lead.user_id) == str(user.id)
        assert lead.email == payload["email"]
        assert lead.destination == "Kyoto"
        assert lead.trip_config_summary == payload["trip_config_summary"]

    mock_send_email.assert_awaited_once_with(
        to_email="traveler@example.com",
        destination="Kyoto",
        trip_config_summary=payload["trip_config_summary"],
    )


async def test_create_agent_lead_rejects_invalid_email(client):
    response = await client.post(
        "/api/agent-leads",
        json={
            "email": "not-an-email",
            "destination": "Kyoto",
            "trip_config_summary": {"pax": 2},
        },
    )

    assert response.status_code == 422


@patch("routers.agent_leads.send_agent_lead_confirmation_email", new_callable=AsyncMock)
async def test_create_agent_lead_allows_anonymous_submission_and_persists_summary(
    mock_send_email,
    client,
    db_session_maker,
):
    mock_send_email.return_value = False
    payload = {
        "email": "guest@example.com",
        "destination": "Bali",
        "trip_config_summary": {
            "dates": {"start": "2026-10-03", "end": "2026-10-09"},
            "pax": 4,
            "budget_tier": "premium",
            "share_url": "/t/demo-share",
        },
    }

    response = await client.post("/api/agent-leads", json=payload)

    assert response.status_code == 200
    lead_id = uuid.UUID(response.json()["id"])

    async with db_session_maker() as session:
        lead = (await session.execute(select(AgentLead).where(AgentLead.id == lead_id))).scalar_one()
        assert lead.user_id is None
        assert lead.trip_config_summary["share_url"] == "/t/demo-share"
        assert lead.trip_config_summary["pax"] == 4


@patch("routers.agent_leads.send_agent_lead_confirmation_email", new_callable=AsyncMock)
async def test_create_agent_lead_ignores_email_send_failure(mock_send_email, client, db_session_maker):
    mock_send_email.return_value = False
    response = await client.post(
        "/api/agent-leads",
        json={
            "email": "traveler@example.com",
            "destination": "Paris",
            "trip_config_summary": {"pax": 2},
        },
    )

    assert response.status_code == 200

    async with db_session_maker() as session:
        leads = (await session.execute(select(AgentLead))).scalars().all()
        assert len(leads) == 1
