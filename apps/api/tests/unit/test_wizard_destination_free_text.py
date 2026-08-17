"""Tests for the destination-from-free-text safety net in the wizard chat
chain (chains/wizard_chat_chain.py) — the fix for the prod bug where a
compact, multi-field opening message (e.g. "bali 6 days for a family of 4 -
leisure - 10-15th nov") left `destination` unset in CURRENT_STATE for the
rest of the conversation, causing the destination-mode chips ("Suggest me!"
/ "I have a destination in mind") to reappear under every subsequent
question regardless of what it actually asked. Nominatim is mocked — fully
offline, per this repo's convention for external-service tests."""
from unittest.mock import AsyncMock, patch

import pytest

from chains.wizard_chat_chain import _infer_destination_from_free_text
from models.common import GeocodeResponse


@pytest.mark.asyncio
async def test_returns_none_for_empty_text():
    assert await _infer_destination_from_free_text(None) is None
    assert await _infer_destination_from_free_text("") is None


@pytest.mark.asyncio
async def test_extracts_leading_place_before_day_count():
    fake = GeocodeResponse(display_name="Denpasar, Bali, Indonesia", lat=-8.65, lon=115.21, country_code="id")
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock(return_value=fake)) as mock_geocode:
        result = await _infer_destination_from_free_text("bali 6 days for a family of 4 - leisure - 10-15th nov")
    mock_geocode.assert_called_once_with("bali")
    assert result == {"city": "Denpasar", "country": "Indonesia", "lat": -8.65, "lon": 115.21}


@pytest.mark.asyncio
async def test_extracts_trip_to_phrasing():
    fake = GeocodeResponse(display_name="Paris, France", lat=48.85, lon=2.35, country_code="fr")
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock(return_value=fake)) as mock_geocode:
        result = await _infer_destination_from_free_text("planning a trip to Paris for our anniversary")
    mock_geocode.assert_called_once_with("Paris")
    assert result == {"city": "Paris", "country": "France", "lat": 48.85, "lon": 2.35}


@pytest.mark.asyncio
async def test_extracts_days_in_phrasing():
    fake = GeocodeResponse(display_name="Denpasar, Bali, Indonesia", lat=-8.65, lon=115.21, country_code="id")
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock(return_value=fake)) as mock_geocode:
        result = await _infer_destination_from_free_text("we want 6 days in Bali with kids")
    mock_geocode.assert_called_once_with("Bali")
    assert result == {"city": "Denpasar", "country": "Indonesia", "lat": -8.65, "lon": 115.21}


@pytest.mark.asyncio
async def test_no_match_for_group_or_budget_follow_ups():
    # These are later-turn answers, not opening trip briefs — no leading
    # place-like phrase before a digit, so no geocode call should even be
    # attempted.
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock()) as mock_geocode:
        assert await _infer_destination_from_free_text("2 adults, 2 kids aged 3,4") is None
        assert await _infer_destination_from_free_text("INR 50K per person") is None
    mock_geocode.assert_not_called()


@pytest.mark.asyncio
async def test_skips_geocoding_stopword_only_candidates():
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock()) as mock_geocode:
        result = await _infer_destination_from_free_text("we want 4 days off next month")
    mock_geocode.assert_not_called()
    assert result is None


@pytest.mark.asyncio
async def test_falls_through_to_next_candidate_on_geocode_failure():
    # Leading-phrase candidate ("we want") fails to geocode; the "days in"
    # phrasing candidate ("Bali") should still be tried and succeed.
    fake = GeocodeResponse(display_name="Denpasar, Bali, Indonesia", lat=-8.65, lon=115.21, country_code="id")

    async def fake_geocode(city, countrycodes=""):
        if city.lower() == "we want":
            raise ValueError("not found")
        return fake

    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock(side_effect=fake_geocode)):
        result = await _infer_destination_from_free_text("we want 4 days in Bali")
    assert result == {"city": "Denpasar", "country": "Indonesia", "lat": -8.65, "lon": 115.21}


@pytest.mark.asyncio
async def test_returns_none_when_all_candidates_fail_to_geocode():
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock(side_effect=ValueError("not found"))):
        result = await _infer_destination_from_free_text("Narnia 6 days for a family of 4")
    assert result is None
