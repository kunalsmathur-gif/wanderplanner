"""Unit/integration tests for the "resume last itinerary" feature (issue
#65): best-effort upsert-on-generation, GET /me/last-itinerary, and the
30-day TTL that hides/clears a stale saved trip.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

import services.user_last_itinerary as user_last_itinerary
from db_models import User, UserLastItinerary
from models.itinerary import ExpenseBreakdown, ItineraryResponse
from models.trip import TripConfig

pytestmark = pytest.mark.asyncio


def _trip_config(**overrides) -> TripConfig:
    base = {
        "purpose": "leisure",
        "dates": {"start": "2026-09-01", "end": "2026-09-05"},
        "scope": "international",
        "origin": {"city": "Delhi", "iata": "DEL", "lat": 28.6, "lon": 77.2},
        "destination": {"city": "Kyoto", "country": "Japan"},
        "destination_mode": "fixed",
        "destination_country": None,
        "hops": [],
        "themes": ["culture"],
        "personas": [],
        "group": {"infants": 0, "kids": [], "adults": 2, "seniors": 0, "pets": 0},
        "accommodation": {
            "style": [], "min_bedrooms": 1, "bathrooms": 1,
            "private_pool": False, "kitchen": False,
            "wheelchair_accessible": False, "pet_friendly": False,
        },
        "pace": "moderate",
        "crowd_preference": "balanced",
        "budget": {"amount": 100000, "currency": "INR"},
        "splurge_categories": [],
        "save_categories": [],
        "prebooked_flights_inr": None,
        "prebooked_accommodation_inr": None,
        "pinned_pois": [],
        "day_cost_preferences": [],
    }
    base.update(overrides)
    return TripConfig.model_validate(base)


def _itinerary() -> ItineraryResponse:
    return ItineraryResponse(
        days=[{
            "day_number": 1,
            "date": "2026-09-01",
            "theme": "Arrival",
            "items": [],
        }],
        alignment_score=0.9,
        expense_breakdown=ExpenseBreakdown(),
        generation_tier="live",
    )


async def _signup_and_get_user(client, db_session_maker, email: str) -> User:
    response = await client.post(
        "/api/auth/signup",
        json={"email": email, "password": "Password123!", "consent_accepted": True},
    )
    assert response.status_code == 200, response.text
    async with db_session_maker() as session:
        return (await session.execute(select(User).where(User.email == email))).scalar_one()


@pytest.fixture(autouse=True)
def _patch_async_session_local(db_session_maker):
    """Route the fire-and-forget writer's independent session onto the same
    in-memory sqlite engine `client`/`db_session_maker` already use, so a
    write via `store_user_last_itinerary` is visible to the test/GET
    endpoint — same pattern as
    tests/unit/test_destination_ingestion.py's `AsyncSessionLocal` patch.
    """
    with patch.object(user_last_itinerary, "AsyncSessionLocal", db_session_maker):
        yield


async def test_no_saved_itinerary_returns_404(client, db_session_maker):
    await _signup_and_get_user(client, db_session_maker, "resume-none@example.com")

    response = await client.get("/api/me/last-itinerary")

    assert response.status_code == 404


async def test_store_then_fetch_returns_saved_trip(client, db_session_maker):
    user = await _signup_and_get_user(client, db_session_maker, "resume-fetch@example.com")

    await user_last_itinerary.store_user_last_itinerary(user.id, _trip_config(), _itinerary())

    response = await client.get("/api/me/last-itinerary")

    assert response.status_code == 200
    body = response.json()
    assert body["trip_config"]["destination"]["city"] == "Kyoto"
    assert body["itinerary"]["days"][0]["theme"] == "Arrival"


async def test_second_generation_overwrites_not_appends(client, db_session_maker):
    """Upsert semantics: a user only ever has one saved-itinerary row, and
    a later generation replaces it rather than adding to a history."""
    user = await _signup_and_get_user(client, db_session_maker, "resume-upsert@example.com")

    await user_last_itinerary.store_user_last_itinerary(user.id, _trip_config(), _itinerary())
    await user_last_itinerary.store_user_last_itinerary(
        user.id, _trip_config(destination={"city": "Osaka", "country": "Japan"}), _itinerary()
    )

    async with db_session_maker() as session:
        rows = (
            await session.execute(select(UserLastItinerary).where(UserLastItinerary.user_id == user.id))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].trip_config_json["destination"]["city"] == "Osaka"


async def test_expired_saved_itinerary_is_treated_as_missing_and_cleaned_up(client, db_session_maker):
    user = await _signup_and_get_user(client, db_session_maker, "resume-expired@example.com")
    await user_last_itinerary.store_user_last_itinerary(user.id, _trip_config(), _itinerary())

    # Backdate updated_at past the 30-day TTL.
    async with db_session_maker() as session:
        row = (
            await session.execute(select(UserLastItinerary).where(UserLastItinerary.user_id == user.id))
        ).scalar_one()
        row.updated_at = datetime.now(UTC) - timedelta(days=31)
        await session.commit()

    response = await client.get("/api/me/last-itinerary")
    assert response.status_code == 404

    # Lazily cleaned up too, not just hidden from the response.
    async with db_session_maker() as session:
        rows = (
            await session.execute(select(UserLastItinerary).where(UserLastItinerary.user_id == user.id))
        ).scalars().all()
        assert rows == []


async def test_saved_itinerary_within_ttl_still_returned(client, db_session_maker):
    user = await _signup_and_get_user(client, db_session_maker, "resume-fresh@example.com")
    await user_last_itinerary.store_user_last_itinerary(user.id, _trip_config(), _itinerary())

    async with db_session_maker() as session:
        row = (
            await session.execute(select(UserLastItinerary).where(UserLastItinerary.user_id == user.id))
        ).scalar_one()
        row.updated_at = datetime.now(UTC) - timedelta(days=29)
        await session.commit()

    response = await client.get("/api/me/last-itinerary")
    assert response.status_code == 200


async def test_write_failure_is_swallowed(client, db_session_maker):
    """A DB error in the best-effort writer must never raise, and must
    leave nothing behind for the GET endpoint to serve."""
    user = await _signup_and_get_user(client, db_session_maker, "resume-failure@example.com")

    def _boom():
        raise RuntimeError("db unavailable")

    with patch.object(user_last_itinerary, "AsyncSessionLocal", _boom):
        await user_last_itinerary.store_user_last_itinerary(user.id, _trip_config(), _itinerary())

    response = await client.get("/api/me/last-itinerary")
    assert response.status_code == 404


async def test_get_user_last_itinerary_is_scoped_to_the_requested_user(db_session_maker):
    """One user's saved trip must never be returned for another user's id."""
    async with db_session_maker() as session:
        user = User(
            email="resume-scope@example.com",
            password_hash="x",
            consent_accepted_at=datetime.now(UTC),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    with patch.object(user_last_itinerary, "AsyncSessionLocal", db_session_maker):
        await user_last_itinerary.store_user_last_itinerary(user.id, _trip_config(), _itinerary())

    async with db_session_maker() as session:
        fetched = await user_last_itinerary.get_user_last_itinerary(session, uuid.uuid4())
        assert fetched is None
        fetched_own = await user_last_itinerary.get_user_last_itinerary(session, user.id)
        assert fetched_own is not None
