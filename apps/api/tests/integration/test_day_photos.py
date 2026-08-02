"""Integration tests for the on-demand day-photo endpoint.

These photos used to be attached during generation, putting a metered Pexels
batch on the critical path of every itinerary for images only the PDF export
renders. `POST /api/day-photos` serves them when the user presses Download,
and the contract that matters is that it degrades rather than fails: a broken
Pexels must cost the user their hero images, never their PDF.
"""
from __future__ import annotations

import pytest

import routers.itinerary as itinerary_router

pytestmark = pytest.mark.asyncio


async def _login(client, email: str, password: str = "Password123!") -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


async def test_requires_an_authenticated_user(client):
    # Unauthenticated this would be an open proxy onto a keyed third-party
    # API, burning our Pexels quota for anyone who finds the route.
    response = await client.post("/api/day-photos", json={"queries": ["Goa beaches"]})

    assert response.status_code == 401


async def test_returns_one_entry_per_query(client, user_factory, monkeypatch):
    await user_factory(email="photos@example.com")
    await _login(client, "photos@example.com")

    async def fake_get_day_photos(queries):
        return [
            {
                "url": f"https://images.pexels.com/{i}.jpg",
                "photographer": "Ada",
                "photographer_url": "https://pexels.com/@ada",
            }
            for i, _ in enumerate(queries)
        ]

    monkeypatch.setattr(itinerary_router, "get_day_photos", fake_get_day_photos)

    response = await client.post(
        "/api/day-photos", json={"queries": ["Goa beaches", "Goa forts"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["url"] == "https://images.pexels.com/0.jpg"
    assert body[0]["photographer"] == "Ada"


async def test_unavailable_photos_become_blank_entries_not_an_error(
    client, user_factory, monkeypatch
):
    # `get_day_photos` returns None per query for a missing API key, a network
    # error or an empty result set. The client relies on positional alignment,
    # so a gap must stay a slot rather than shortening the list.
    await user_factory(email="blank@example.com")
    await _login(client, "blank@example.com")

    async def fake_get_day_photos(queries):
        return [None, {"url": "https://images.pexels.com/1.jpg", "photographer": "", "photographer_url": ""}, None]

    monkeypatch.setattr(itinerary_router, "get_day_photos", fake_get_day_photos)

    response = await client.post(
        "/api/day-photos", json={"queries": ["a", "b", "c"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    assert body[0] == {"url": "", "photographer": "", "photographer_url": ""}
    assert body[1]["url"] == "https://images.pexels.com/1.jpg"
    assert body[2]["url"] == ""


async def test_empty_query_list_is_valid(client, user_factory):
    # A PDF with no days is degenerate but not an error, and the client should
    # not have to special-case it before asking.
    await user_factory(email="empty@example.com")
    await _login(client, "empty@example.com")

    response = await client.post("/api/day-photos", json={"queries": []})

    assert response.status_code == 200
    assert response.json() == []


async def test_rejects_more_queries_than_a_trip_can_have(client, user_factory):
    # One Pexels call per query, so list length is a direct cost multiplier —
    # the bound is what stops a single request fanning out arbitrarily.
    await user_factory(email="toomany@example.com")
    await _login(client, "toomany@example.com")

    response = await client.post(
        "/api/day-photos", json={"queries": [f"day {i}" for i in range(61)]}
    )

    assert response.status_code == 422
