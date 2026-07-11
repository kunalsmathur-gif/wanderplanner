"""Integration test for auth gating on itinerary generation."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_generate_itinerary_requires_authenticated_user(client):
    response = await client.post(
        "/api/generate-itinerary",
        json={
            "trip_config": {
                "destination": {"city": "Kyoto", "country": "Japan"},
                "budget": {"amount": 1000, "currency": "USD"},
            }
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
