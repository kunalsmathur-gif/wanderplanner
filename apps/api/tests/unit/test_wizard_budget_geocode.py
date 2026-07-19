"""Tests for the origin/destination geocoding wired into the wizard chat's
budget-estimate flow (chains/wizard_chat_chain.py). Nominatim is mocked —
fully offline, per this repo's convention for external-service tests."""
from unittest.mock import AsyncMock, patch

import pytest

from chains.wizard_chat_chain import _ensure_place_coords, _has_group, _resolve_origin_destination_coords
from models.common import GeocodeResponse


def test_has_group_false_when_empty():
    assert _has_group({}) is False
    assert _has_group({"group": {}}) is False


def test_has_group_true_when_any_headcount_set():
    assert _has_group({"group": {"adults": 2}}) is True


@pytest.mark.asyncio
async def test_ensure_place_coords_skips_when_already_resolved():
    place = {"city": "Bengaluru", "lat": 12.9716, "lon": 77.5946}
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock()) as mock_geocode:
        result = await _ensure_place_coords(place)
    assert result is None
    mock_geocode.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_place_coords_geocodes_when_missing():
    place = {"city": "Bengaluru"}
    fake_response = GeocodeResponse(
        display_name="Bengaluru, India", lat=12.9716, lon=77.5946, country_code="in", is_country=False
    )
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock(return_value=fake_response)):
        result = await _ensure_place_coords(place)
    assert result == {"lat": 12.9716, "lon": 77.5946}


@pytest.mark.asyncio
async def test_ensure_place_coords_never_raises_on_geocode_failure():
    place = {"city": "Nowhereville"}
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock(side_effect=ValueError("not found"))):
        result = await _ensure_place_coords(place)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_coords_skips_geocoding_until_group_dest_origin_all_known():
    # Missing group -> no geocode calls at all, even though destination/origin
    # cities are both present (avoid burning Nominatim calls on turns where
    # the estimate can't be used yet anyway).
    config = {
        "destination": {"city": "Colombo"},
        "origin": {"city": "Bengaluru"},
    }
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock()) as mock_geocode:
        patch_result = await _resolve_origin_destination_coords(config)
    assert patch_result == {}
    mock_geocode.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_coords_geocodes_both_once_all_known():
    config = {
        "group": {"adults": 2},
        "destination": {"city": "Colombo"},
        "origin": {"city": "Bengaluru"},
    }
    fake_response = GeocodeResponse(
        display_name="x", lat=1.0, lon=2.0, country_code="in", is_country=False
    )
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock(return_value=fake_response)):
        patch_result = await _resolve_origin_destination_coords(config)
    assert patch_result == {"origin": {"lat": 1.0, "lon": 2.0}, "destination": {"lat": 1.0, "lon": 2.0}}
