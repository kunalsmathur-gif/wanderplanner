"""Tests for the departure-city (origin) ambiguity sanity check added to
chains/wizard_chat_chain.py. Real bug fixed here: a bare "MUM" (not
actually Mumbai's IATA code) top-hits an unrelated Ohio university via
Nominatim, and a bare "NY" top-hits the STATE of New York rather than a
city — both silently corrupted downstream flight-cost estimates before
this check existed. Nominatim is mocked — fully offline, per this repo's
convention for external-service tests."""
from unittest.mock import AsyncMock, patch

import pytest

from chains.wizard_chat_chain import (
    _looks_like_ambiguous_place_code,
    _origin_ambiguity_warning,
)
from models.common import GeocodeResponse


@pytest.mark.parametrize("text", ["NY", "SF", "LA", "BOM", "MUM", "BLR", "ny", "sf"])
def test_looks_like_ambiguous_place_code_flags_short_tokens(text):
    assert _looks_like_ambiguous_place_code(text) is True


@pytest.mark.parametrize("text", ["Mumbai", "Bombay", "New York", "San Francisco", "Detroit", ""])
def test_looks_like_ambiguous_place_code_allows_real_names(text):
    assert _looks_like_ambiguous_place_code(text) is False


@pytest.mark.asyncio
async def test_origin_ambiguity_warning_none_when_no_origin():
    assert await _origin_ambiguity_warning(None) is None
    assert await _origin_ambiguity_warning({}) is None


@pytest.mark.asyncio
async def test_origin_ambiguity_warning_flags_short_code_without_geocoding():
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock()) as mock_geocode:
        result = await _origin_ambiguity_warning({"city": "MUM"})
    assert result is not None
    message, chips = result
    assert "MUM" in message
    mock_geocode.assert_not_called()


@pytest.mark.asyncio
async def test_origin_ambiguity_warning_none_for_confident_geocode():
    fake_response = GeocodeResponse(
        display_name="Detroit, Michigan, USA", lat=42.33, lon=-83.04, country_code="us", is_country=False
    )
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock(return_value=fake_response)):
        result = await _origin_ambiguity_warning({"city": "Detroit"})
    assert result is None


@pytest.mark.asyncio
async def test_origin_ambiguity_warning_flags_low_confidence_geocode():
    fake_response = GeocodeResponse(
        display_name="Some Ambiguous Place", lat=0.0, lon=0.0, country_code="xx", is_country=False,
        low_confidence=True,
    )
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock(return_value=fake_response)):
        result = await _origin_ambiguity_warning({"city": "Springfield"})
    assert result is not None
    message, chips = result
    assert "Some Ambiguous Place" in message
    assert chips


@pytest.mark.asyncio
async def test_origin_ambiguity_warning_handles_geocode_failure():
    with patch("chains.wizard_chat_chain.geocode_city", new=AsyncMock(side_effect=ValueError("not found"))):
        result = await _origin_ambiguity_warning({"city": "Xyzzyville"})
    assert result is not None
    message, chips = result
    assert "Xyzzyville" in message
