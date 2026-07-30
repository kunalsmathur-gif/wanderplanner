"""Integration tests for the itinerary feedback endpoints — implements
FEEDBACK-001..005 from docs/eval-set.md section 12.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from db_models import ItineraryFeedback

pytestmark = pytest.mark.asyncio


_TRIP_CONFIG_SNAPSHOT = {
    "destination": {"city": "Kyoto", "country": "Japan"},
    "dates": {"start": "2026-09-01", "end": "2026-09-07"},
    "budget": {"total_inr": 80000},
    "pace": "moderate",
    "themes": ["culture", "food"],
    "pinned_pois": [],
}


async def test_itinerary_level_missed_the_mark_persists_with_request_context(client, db_session_maker):
    """FEEDBACK-001."""
    payload = {
        "trip_config_snapshot": _TRIP_CONFIG_SNAPSHOT,
        "scope": "itinerary",
        "sentiment": "missed_the_mark",
        "note": "Too touristy for what I asked for.",
    }

    response = await client.post("/api/itinerary-feedback", json=payload)

    assert response.status_code == 200
    feedback_id = uuid.UUID(response.json()["id"])

    async with db_session_maker() as session:
        row = (
            await session.execute(select(ItineraryFeedback).where(ItineraryFeedback.id == feedback_id))
        ).scalar_one()
        assert row.scope == "itinerary"
        assert row.sentiment == "missed_the_mark"
        assert row.day_index is None
        assert row.place_ref is None
        assert row.trip_config_snapshot == _TRIP_CONFIG_SNAPSHOT


async def test_day_scope_requires_day_index(client):
    """FEEDBACK-002."""
    response = await client.post(
        "/api/itinerary-feedback",
        json={
            "trip_config_snapshot": _TRIP_CONFIG_SNAPSHOT,
            "scope": "day",
            "sentiment": "thumbs_down",
        },
    )

    assert response.status_code == 422
    assert "day_index" in response.text


async def test_place_scope_requires_place_ref(client):
    """FEEDBACK-003."""
    response = await client.post(
        "/api/itinerary-feedback",
        json={
            "trip_config_snapshot": _TRIP_CONFIG_SNAPSHOT,
            "scope": "place",
            "day_index": 2,
            "sentiment": "thumbs_down",
        },
    )

    assert response.status_code == 422
    assert "place_ref" in response.text


async def test_day_scope_thumbs_down_persists_correctly(client, db_session_maker):
    """FEEDBACK-004."""
    payload = {
        "trip_config_snapshot": _TRIP_CONFIG_SNAPSHOT,
        "scope": "day",
        "day_index": 3,
        "sentiment": "thumbs_down",
    }

    response = await client.post("/api/itinerary-feedback", json=payload)

    assert response.status_code == 200
    feedback_id = uuid.UUID(response.json()["id"])

    async with db_session_maker() as session:
        row = (
            await session.execute(select(ItineraryFeedback).where(ItineraryFeedback.id == feedback_id))
        ).scalar_one()
        assert row.scope == "day"
        assert row.day_index == 3
        assert row.sentiment == "thumbs_down"
        assert row.trip_config_snapshot == _TRIP_CONFIG_SNAPSHOT


async def test_feedback_snapshot_survives_later_trip_config_change(client, db_session_maker):
    """FEEDBACK-005 — the snapshot stored at submit time must not be a live
    reference: mutating the payload dict after the request completes (as a
    stand-in for the user later editing/regenerating their trip config) must
    not affect the persisted row.
    """
    snapshot = dict(_TRIP_CONFIG_SNAPSHOT)
    payload = {
        "trip_config_snapshot": snapshot,
        "scope": "place",
        "day_index": 1,
        "place_ref": "Fushimi Inari Shrine",
        "sentiment": "thumbs_up",
    }

    response = await client.post("/api/itinerary-feedback", json=payload)
    assert response.status_code == 200
    feedback_id = uuid.UUID(response.json()["id"])

    # Simulate the trip config being edited afterwards.
    snapshot["budget"] = {"total_inr": 150000}
    snapshot["pace"] = "relaxed"

    async with db_session_maker() as session:
        row = (
            await session.execute(select(ItineraryFeedback).where(ItineraryFeedback.id == feedback_id))
        ).scalar_one()
        assert row.trip_config_snapshot["budget"] == {"total_inr": 80000}
        assert row.trip_config_snapshot["pace"] == "moderate"


async def test_update_feedback_changes_sentiment_in_place(client, db_session_maker):
    """Vote-change flow: PATCH flips sentiment on the same row rather than
    creating a duplicate.
    """
    create_response = await client.post(
        "/api/itinerary-feedback",
        json={
            "trip_config_snapshot": _TRIP_CONFIG_SNAPSHOT,
            "scope": "place",
            "day_index": 2,
            "place_ref": "Arashiyama Bamboo Grove",
            "sentiment": "thumbs_up",
        },
    )
    assert create_response.status_code == 200
    feedback_id = create_response.json()["id"]

    update_response = await client.patch(
        f"/api/itinerary-feedback/{feedback_id}",
        json={"sentiment": "thumbs_down"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["sentiment"] == "thumbs_down"

    async with db_session_maker() as session:
        rows = (
            await session.execute(
                select(ItineraryFeedback).where(ItineraryFeedback.place_ref == "Arashiyama Bamboo Grove")
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].sentiment == "thumbs_down"


async def test_update_feedback_404_for_unknown_id(client):
    response = await client.patch(
        f"/api/itinerary-feedback/{uuid.uuid4()}",
        json={"sentiment": "thumbs_up"},
    )

    assert response.status_code == 404
