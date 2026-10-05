"""Unit tests for chains/workation_recommend_chain.py.

Mocks the three prior-workstream modules this chain orchestrates
(`get_long_weekends`, Qdrant retrieval via `core.qdrant.get_qdrant`,
`find_workation_venues`) plus `geocode_city` and the Gemini client, mirroring
the patching conventions used in tests/unit/test_itinerary_timing.py
(`monkeypatch.setattr(settings, ...)`) and tests/unit/test_workation_venues.py
(patching collaborators directly rather than their transports).

Covers:
- happy path with matches — every destination and event carries lat/lon.
- no-match "nothing found" path — has_results=False, no fabricated destination.
- LLM-failure fallback path — a broken/absent Gemini client still returns a
  usable (templated) rationale rather than raising.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chains.workation_recommend_chain import (
    WorkationRecommendRequest,
    recommend_workation,
)
from core.config import settings
from models.common import GeocodeResponse
from services.long_weekend import LongWeekendWindow
from services.workation_venues import WorkationVenueResult


def _window(start: date, end: date, days_off: int, leave_days: int = 0, reason: str = "Test Holiday + weekend") -> LongWeekendWindow:
    return LongWeekendWindow(
        start_date=start,
        end_date=end,
        total_days_off=days_off,
        leave_days_needed=leave_days,
        reason=reason,
        value=days_off / max(leave_days, 1),
    )


def _geocode(lat: float, lon: float, name: str = "Place") -> GeocodeResponse:
    return GeocodeResponse(display_name=name, lat=lat, lon=lon, country_code="in")


def _qdrant_hit(score: float, payload: dict) -> MagicMock:
    hit = MagicMock()
    hit.score = score
    hit.payload = payload
    return hit


def _event_payload(
    name: str = "Hampi Utsav",
    location: str = "Hampi, Karnataka",
    start: str = "2026-11-14",
    end: str = "2026-11-16",
    category: str = "culture",
) -> dict:
    return {
        "name": name,
        "start_date": start,
        "end_date": end,
        "location": location,
        "interest_category": category,
        "source_citation": "Karnataka Tourism",
        "deep_link": None,
    }


def _venue_result(found: int = 5, wifi: int = 2, limited: bool = False) -> WorkationVenueResult:
    return WorkationVenueResult(
        venues=[],
        total_venues_found=found,
        venues_with_verified_wifi_count=wifi,
        has_limited_coverage=limited,
    )


@pytest.fixture(autouse=True)
def _mock_embed():
    with patch("chains.workation_recommend_chain.embed", return_value=[[0.1] * 384]):
        yield


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_matches_produce_destinations_with_lat_lon(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "llm_provider", "mock")

        window = _window(date(2026, 11, 14), date(2026, 11, 16), days_off=3, leave_days=1)

        with patch("chains.workation_recommend_chain.get_long_weekends", return_value=[window]), \
             patch("chains.workation_recommend_chain.get_qdrant") as mock_get_qdrant, \
             patch("chains.workation_recommend_chain.geocode_city", new_callable=AsyncMock) as mock_geocode, \
             patch("chains.workation_recommend_chain.find_workation_venues", new_callable=AsyncMock) as mock_venues:

            mock_client = MagicMock()
            mock_client.search.return_value = [
                _qdrant_hit(0.9, _event_payload()),
            ]
            mock_get_qdrant.return_value = mock_client

            mock_geocode.return_value = _geocode(15.335, 76.46, "Hampi")
            mock_venues.return_value = _venue_result()

            request = WorkationRecommendRequest(state="Karnataka", interests=["culture"])
            response = await recommend_workation(request)

        assert response.has_results is True
        assert len(response.destinations) == 1
        dest = response.destinations[0]
        assert dest.destination == "Hampi"
        assert dest.lat == pytest.approx(15.335)
        assert dest.lon == pytest.approx(76.46)
        assert dest.rationale  # mock rationale filled in
        assert len(dest.matching_events) == 1
        event = dest.matching_events[0]
        assert event.lat == pytest.approx(15.335)
        assert event.lon == pytest.approx(76.46)
        assert "WFH" in dest.workation_split or "exploring" in dest.workation_split
        assert response.long_weekends[0].total_days_off == 3

    @pytest.mark.asyncio
    async def test_geocode_failure_drops_destination_not_whole_response(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "llm_provider", "mock")
        window = _window(date(2026, 11, 14), date(2026, 11, 16), days_off=3, leave_days=1)

        with patch("chains.workation_recommend_chain.get_long_weekends", return_value=[window]), \
             patch("chains.workation_recommend_chain.get_qdrant") as mock_get_qdrant, \
             patch("chains.workation_recommend_chain.geocode_city", new_callable=AsyncMock) as mock_geocode, \
             patch("chains.workation_recommend_chain.find_workation_venues", new_callable=AsyncMock) as mock_venues:

            mock_client = MagicMock()
            mock_client.search.return_value = [_qdrant_hit(0.9, _event_payload())]
            mock_get_qdrant.return_value = mock_client
            mock_geocode.side_effect = ValueError("Location not found")
            mock_venues.return_value = _venue_result()

            request = WorkationRecommendRequest(state="Karnataka", interests=["culture"])
            response = await recommend_workation(request)

        assert response.has_results is False
        assert response.destinations == []
        assert response.message


class TestNoMatches:
    @pytest.mark.asyncio
    async def test_no_events_returns_honest_empty_result(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "llm_provider", "mock")
        window = _window(date(2026, 11, 14), date(2026, 11, 16), days_off=3, leave_days=1)

        with patch("chains.workation_recommend_chain.get_long_weekends", return_value=[window]), \
             patch("chains.workation_recommend_chain.get_qdrant") as mock_get_qdrant:
            mock_client = MagicMock()
            mock_client.search.return_value = []
            mock_get_qdrant.return_value = mock_client

            request = WorkationRecommendRequest(state="Karnataka", interests=["music"])
            response = await recommend_workation(request)

        assert response.has_results is False
        assert response.destinations == []
        assert "No events" in response.message

    @pytest.mark.asyncio
    async def test_no_long_weekends_returns_honest_empty_result(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "llm_provider", "mock")

        with patch("chains.workation_recommend_chain.get_long_weekends", return_value=[]):
            request = WorkationRecommendRequest(state="Karnataka", interests=["music"])
            response = await recommend_workation(request)

        assert response.has_results is False
        assert response.destinations == []
        assert "No upcoming long weekends" in response.message

    @pytest.mark.asyncio
    async def test_date_range_filters_out_non_overlapping_windows(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "llm_provider", "mock")
        window = _window(date(2026, 11, 14), date(2026, 11, 16), days_off=3, leave_days=1)

        with patch("chains.workation_recommend_chain.get_long_weekends", return_value=[window]):
            request = WorkationRecommendRequest(
                state="Karnataka", interests=["music"], date_range=("2026-01-01", "2026-01-31")
            )
            response = await recommend_workation(request)

        assert response.has_results is False
        assert response.destinations == []
        assert "No long weekend" in response.message

    @pytest.mark.asyncio
    async def test_date_range_overlapping_window_still_matches(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "llm_provider", "mock")
        window = _window(date(2026, 11, 14), date(2026, 11, 16), days_off=3, leave_days=1)

        with patch("chains.workation_recommend_chain.get_long_weekends", return_value=[window]), \
             patch("chains.workation_recommend_chain.get_qdrant") as mock_get_qdrant, \
             patch("chains.workation_recommend_chain.geocode_city", new_callable=AsyncMock) as mock_geocode, \
             patch("chains.workation_recommend_chain.find_workation_venues", new_callable=AsyncMock) as mock_venues:
            mock_client = MagicMock()
            mock_client.search.return_value = [_qdrant_hit(0.9, _event_payload())]
            mock_get_qdrant.return_value = mock_client
            mock_geocode.return_value = _geocode(15.335, 76.46, "Hampi")
            mock_venues.return_value = _venue_result()

            request = WorkationRecommendRequest(
                state="Karnataka", interests=["culture"], date_range=("2026-11-10", "2026-11-20")
            )
            response = await recommend_workation(request)

        assert response.has_results is True
        assert len(response.destinations) == 1

    @pytest.mark.asyncio
    async def test_low_score_hits_filtered_out(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "llm_provider", "mock")
        window = _window(date(2026, 11, 14), date(2026, 11, 16), days_off=3, leave_days=1)

        with patch("chains.workation_recommend_chain.get_long_weekends", return_value=[window]), \
             patch("chains.workation_recommend_chain.get_qdrant") as mock_get_qdrant:
            mock_client = MagicMock()
            mock_client.search.return_value = [_qdrant_hit(0.05, _event_payload())]
            mock_get_qdrant.return_value = mock_client

            request = WorkationRecommendRequest(state="Karnataka", interests=["music"])
            response = await recommend_workation(request)

        assert response.has_results is False


class TestLLMFallback:
    @pytest.mark.asyncio
    async def test_gemini_failure_falls_back_to_mock_rationale(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "llm_provider", "gemini")
        monkeypatch.setattr(settings, "gemini_api_key", "fake-key")

        window = _window(date(2026, 11, 14), date(2026, 11, 16), days_off=3, leave_days=1)

        with patch("chains.workation_recommend_chain.get_long_weekends", return_value=[window]), \
             patch("chains.workation_recommend_chain.get_qdrant") as mock_get_qdrant, \
             patch("chains.workation_recommend_chain.geocode_city", new_callable=AsyncMock) as mock_geocode, \
             patch("chains.workation_recommend_chain.find_workation_venues", new_callable=AsyncMock) as mock_venues, \
             patch("google.genai.Client") as mock_genai_client:

            mock_client = MagicMock()
            mock_client.search.return_value = [_qdrant_hit(0.9, _event_payload())]
            mock_get_qdrant.return_value = mock_client

            mock_geocode.return_value = _geocode(15.335, 76.46, "Hampi")
            mock_venues.return_value = _venue_result()

            mock_genai_client.return_value.models.generate_content.side_effect = RuntimeError("network down")

            request = WorkationRecommendRequest(state="Karnataka", interests=["culture"])
            response = await recommend_workation(request)

        assert response.has_results is True
        assert len(response.destinations) == 1
        assert response.destinations[0].rationale  # fell back to templated text, didn't crash

    @pytest.mark.asyncio
    async def test_missing_api_key_falls_back_to_mock_rationale(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "llm_provider", "gemini")
        monkeypatch.setattr(settings, "gemini_api_key", "")

        window = _window(date(2026, 11, 14), date(2026, 11, 16), days_off=3, leave_days=1)

        with patch("chains.workation_recommend_chain.get_long_weekends", return_value=[window]), \
             patch("chains.workation_recommend_chain.get_qdrant") as mock_get_qdrant, \
             patch("chains.workation_recommend_chain.geocode_city", new_callable=AsyncMock) as mock_geocode, \
             patch("chains.workation_recommend_chain.find_workation_venues", new_callable=AsyncMock) as mock_venues:

            mock_client = MagicMock()
            mock_client.search.return_value = [_qdrant_hit(0.9, _event_payload())]
            mock_get_qdrant.return_value = mock_client
            mock_geocode.return_value = _geocode(15.335, 76.46, "Hampi")
            mock_venues.return_value = _venue_result()

            request = WorkationRecommendRequest(state="Karnataka", interests=["culture"])
            response = await recommend_workation(request)

        assert response.has_results is True
        assert response.destinations[0].rationale
