"""Tests for `routers/workation.py` — the HTTP layer only. The underlying
`get_long_weekends`/`recommend_workation` logic is covered by their own unit
tests (`services/long_weekend.py`, `chains/workation_recommend_chain.py`);
here we just verify routing, status codes, and error sanitization using the
same `client` fixture (httpx `AsyncClient` over the real `main.app`) the rest
of the router test suite relies on (see tests/conftest.py).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from chains.workation_recommend_chain import WorkationRecommendResponse


@pytest.mark.asyncio
async def test_long_weekends_success(client):
    resp = await client.get("/api/workation/long-weekends", params={"state": "Karnataka", "year": 2026})
    assert resp.status_code == 200
    body = resp.json()
    assert "windows" in body
    assert isinstance(body["windows"], list)
    if body["windows"]:
        window = body["windows"][0]
        assert {"start_date", "end_date", "total_days_off", "leave_days_needed", "reason", "value"} <= window.keys()


@pytest.mark.asyncio
async def test_long_weekends_defaults_year_when_omitted(client):
    resp = await client.get("/api/workation/long-weekends", params={"state": "Karnataka"})
    assert resp.status_code == 200
    assert "windows" in resp.json()


@pytest.mark.asyncio
async def test_long_weekends_invalid_state_returns_400(client):
    resp = await client.get("/api/workation/long-weekends", params={"state": "Narnia", "year": 2026})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Narnia" not in detail  # sanitize_error must not leak raw exception text
    assert "ref:" in detail


@pytest.mark.asyncio
async def test_workation_recommend_success(client):
    mock_response = WorkationRecommendResponse(
        long_weekends=[],
        destinations=[],
        has_results=False,
        message="No upcoming long weekends found for Karnataka.",
    )
    with patch(
        "routers.workation.recommend_workation", new=AsyncMock(return_value=mock_response)
    ) as mocked:
        resp = await client.post(
            "/api/workation/recommend",
            json={"state": "Karnataka", "interests": ["music", "food"]},
        )
    assert resp.status_code == 200
    assert resp.json()["has_results"] is False
    mocked.assert_awaited_once()


@pytest.mark.asyncio
async def test_workation_recommend_handles_unexpected_error(client):
    with patch(
        "routers.workation.recommend_workation",
        new=AsyncMock(side_effect=RuntimeError("boom - qdrant down")),
    ):
        resp = await client.post(
            "/api/workation/recommend",
            json={"state": "Karnataka", "interests": ["music"]},
        )
    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert "boom" not in detail
    assert "ref:" in detail


@pytest.mark.asyncio
async def test_workation_recommend_validates_request_body(client):
    resp = await client.post("/api/workation/recommend", json={"interests": ["music"]})
    assert resp.status_code == 422
