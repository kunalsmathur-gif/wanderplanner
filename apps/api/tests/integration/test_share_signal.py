"""Integration tests for POST /api/share's generation_id → 'shared' signal
wiring (issue #34, slice 3).

`get_cache()` is mocked in every test here — `.env` in this environment
points `REDIS_URL` at a real remote Redis, and these tests must never make
live network calls to it (also avoids flakiness/cross-test event-loop
issues from a real network client living past a closed test loop).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio

_PAYLOAD = {
    "itinerary": {"days": []},
    "trip_config": {"destination": {"city": "Kyoto"}},
}


def _fake_cache() -> MagicMock:
    cache = MagicMock()
    cache.set_json = AsyncMock()
    return cache


async def test_share_with_generation_id_records_shared_signal(client):
    with patch("routers.share.get_cache", return_value=_fake_cache()), \
         patch("routers.share.record_share_signal", new=AsyncMock()) as mock_signal:
        response = await client.post("/api/share", json={**_PAYLOAD, "generation_id": "42"})
        # Let the fire-and-forget asyncio.create_task tick over before the
        # test's event loop closes — otherwise the still-pending task gets
        # torn down mid-flight and its "never retrieved" warning surfaces as
        # a failure on a *later*, unrelated test instead of this one.
        await asyncio.sleep(0)

    assert response.status_code == 200
    # AsyncMock records the call synchronously (creating the coroutine
    # happens at call time, before asyncio.create_task ever schedules it),
    # so this assertion doesn't race the fire-and-forget task.
    mock_signal.assert_called_once_with("42")


async def test_share_without_generation_id_does_not_record_a_signal(client):
    with patch("routers.share.get_cache", return_value=_fake_cache()), \
         patch("routers.share.record_share_signal", new=AsyncMock()) as mock_signal:
        response = await client.post("/api/share", json=_PAYLOAD)

    assert response.status_code == 200
    mock_signal.assert_not_called()
