"""Integration tests for POST /api/generation-signal (issue #34)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from db_models import GeneratedItinerarySignal

pytestmark = pytest.mark.asyncio


async def test_first_signal_creates_a_row(client, db_session_maker):
    response = await client.post(
        "/api/generation-signal",
        json={"generation_id": "12345", "event": "regenerated"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "recorded"}

    async with db_session_maker() as session:
        row = (
            await session.execute(
                select(GeneratedItinerarySignal).where(GeneratedItinerarySignal.generation_id == "12345")
            )
        ).scalar_one()
        assert row.regenerated_count == 1
        assert row.post_gen_chat_turns == 0
        assert row.was_shared is False


async def test_repeated_events_accumulate_on_the_same_row(client, db_session_maker):
    for _ in range(2):
        await client.post(
            "/api/generation-signal",
            json={"generation_id": "999", "event": "regenerated"},
        )
    await client.post(
        "/api/generation-signal",
        json={"generation_id": "999", "event": "chat_turn"},
    )
    await client.post(
        "/api/generation-signal",
        json={"generation_id": "999", "event": "chat_turn"},
    )

    async with db_session_maker() as session:
        row = (
            await session.execute(
                select(GeneratedItinerarySignal).where(GeneratedItinerarySignal.generation_id == "999")
            )
        ).scalar_one()
        assert row.regenerated_count == 2
        assert row.post_gen_chat_turns == 2


async def test_session_duration_sets_not_increments(client, db_session_maker):
    await client.post(
        "/api/generation-signal",
        json={"generation_id": "777", "event": "session_duration", "value": 45},
    )
    response = await client.post(
        "/api/generation-signal",
        json={"generation_id": "777", "event": "session_duration", "value": 200},
    )
    assert response.status_code == 200

    async with db_session_maker() as session:
        row = (
            await session.execute(
                select(GeneratedItinerarySignal).where(GeneratedItinerarySignal.generation_id == "777")
            )
        ).scalar_one()
        assert row.session_duration_s == 200


async def test_session_duration_requires_value(client):
    response = await client.post(
        "/api/generation-signal",
        json={"generation_id": "111", "event": "session_duration"},
    )
    assert response.status_code == 422


async def test_shared_event_not_accepted_from_this_endpoint(client):
    """Shared is set internally by routers/share.py, not by the client
    beacon — this endpoint should reject it as an unknown event type."""
    response = await client.post(
        "/api/generation-signal",
        json={"generation_id": "222", "event": "shared"},
    )
    assert response.status_code == 422
