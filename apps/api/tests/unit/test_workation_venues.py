"""Unit tests for services/workation_venues.py.

Covers the three behaviours called out in docs/plans/india-workation-finder-plan.md:
wifi tag parsing (`wifi=yes` vs `internet_access=wlan` vs no tag at all), graceful
degradation when wifi tagging is sparse for a destination, and category filtering
(cafe/hotel/coworking only — other OSM tags must not leak into the shortlist).

Mocking convention mirrors tests/unit/test_osm_scraper.py: Overpass is reached via
`httpx.AsyncClient`, so the client is mocked at `services.workation_venues.httpx.
AsyncClient` and `geocode_city` is patched directly rather than mocking Nominatim too.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.common import GeocodeResponse
from services.workation_venues import (
    _address_from_tags,
    _element_to_venue,
    _venue_category,
    _wifi_signal,
    find_workation_venues,
)


def _make_element(osm_id: int, name: str, tags: dict[str, str], lat: float = 12.97, lon: float = 77.59) -> dict:
    return {"id": osm_id, "type": "node", "lat": lat, "lon": lon, "tags": {"name": name, **tags}}


def _make_response(elements: list[dict]) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"elements": elements}
    return response


def _mock_client(*responses) -> AsyncMock:
    client = AsyncMock()
    client.post = AsyncMock(side_effect=list(responses))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _fake_geocode() -> GeocodeResponse:
    return GeocodeResponse(
        display_name="Bengaluru, India",
        lat=12.9716,
        lon=77.5946,
        country_code="in",
    )


class TestWifiSignal:
    def test_internet_access_wlan_is_affirmative(self):
        has_wifi, source = _wifi_signal({"internet_access": "wlan"})
        assert has_wifi is True
        assert source == "internet_access=wlan"

    def test_internet_access_yes_is_affirmative(self):
        has_wifi, source = _wifi_signal({"internet_access": "yes"})
        assert has_wifi is True
        assert source == "internet_access=yes"

    def test_wifi_yes_is_affirmative(self):
        has_wifi, source = _wifi_signal({"wifi": "yes"})
        assert has_wifi is True
        assert source == "wifi=yes"

    def test_internet_access_no_is_not_affirmative(self):
        """A `no`/`terminal` tag is evidence against wifi, not for it, and
        must not be surfaced as a citation."""
        has_wifi, source = _wifi_signal({"internet_access": "no"})
        assert has_wifi is False
        assert source == ""

    def test_no_tag_at_all_is_not_affirmative(self):
        has_wifi, source = _wifi_signal({})
        assert has_wifi is False
        assert source == ""


class TestVenueCategory:
    def test_cafe_tag_maps_to_cafe(self):
        assert _venue_category({"amenity": "cafe"}) == "cafe"

    def test_hotel_tag_maps_to_hotel(self):
        assert _venue_category({"tourism": "hotel"}) == "hotel"

    def test_coworking_tag_maps_to_coworking(self):
        assert _venue_category({"office": "coworking"}) == "coworking"

    def test_unrelated_tag_is_not_a_venue(self):
        assert _venue_category({"amenity": "restaurant"}) is None
        assert _venue_category({"tourism": "museum"}) is None


class TestAddressFromTags:
    def test_assembles_available_parts(self):
        addr = _address_from_tags({
            "addr:housenumber": "12",
            "addr:street": "MG Road",
            "addr:city": "Bengaluru",
        })
        assert addr == "12, MG Road, Bengaluru"

    def test_empty_when_no_addr_tags(self):
        assert _address_from_tags({"amenity": "cafe"}) == ""


class TestElementToVenue:
    def test_unnamed_node_is_skipped(self):
        element = _make_element(1, "", {"amenity": "cafe"})
        element["tags"] = {"amenity": "cafe"}  # no name key at all
        assert _element_to_venue(element) is None

    def test_non_venue_tag_is_skipped(self):
        element = _make_element(2, "Some Museum", {"tourism": "museum"})
        assert _element_to_venue(element) is None

    def test_way_center_coordinates_are_used(self):
        element = {
            "id": 3, "type": "way",
            "center": {"lat": 12.9, "lon": 77.6},
            "tags": {"name": "Hotel Grand", "tourism": "hotel"},
        }
        venue = _element_to_venue(element)
        assert venue is not None
        assert venue.lat == 12.9 and venue.lon == 77.6

    def test_wifi_tag_is_carried_through_as_provenance(self):
        element = _make_element(4, "Third Wave Coffee", {"amenity": "cafe", "wifi": "yes"})
        venue = _element_to_venue(element)
        assert venue.has_verified_wifi is True
        assert venue.wifi_tag_source == "wifi=yes"


class TestFindWorkationVenues:
    @pytest.mark.asyncio
    async def test_category_filtering_excludes_unrelated_pois(self):
        elements = [
            _make_element(1, "Cafe Coffee Day", {"amenity": "cafe", "internet_access": "wlan"}),
            _make_element(2, "Taj Hotel", {"tourism": "hotel"}),
            _make_element(3, "Some Temple", {"amenity": "place_of_worship"}),
            _make_element(4, "WeWork", {"office": "coworking", "wifi": "yes"}),
        ]
        client = _mock_client(_make_response(elements))
        with patch("services.workation_venues.httpx.AsyncClient", return_value=client), \
             patch("services.workation_venues.geocode_city", new=AsyncMock(return_value=_fake_geocode())):
            result = await find_workation_venues("Bengaluru")

        names = {v.name for v in result.venues}
        assert names == {"Cafe Coffee Day", "Taj Hotel", "WeWork"}
        assert result.total_venues_found == 3

    @pytest.mark.asyncio
    async def test_graceful_degradation_when_wifi_tags_are_sparse(self):
        """Most OSM nodes in an Indian city carry no wifi tag at all — the
        shortlist should still be returned (not fabricated), but flagged as
        limited coverage so the frontend can disclaim it."""
        elements = [
            _make_element(1, "Cafe A", {"amenity": "cafe"}),
            _make_element(2, "Cafe B", {"amenity": "cafe"}),
            _make_element(3, "Cafe C", {"amenity": "cafe"}),
            _make_element(4, "Cafe D (verified)", {"amenity": "cafe", "internet_access": "wlan"}),
        ]
        client = _mock_client(_make_response(elements))
        with patch("services.workation_venues.httpx.AsyncClient", return_value=client), \
             patch("services.workation_venues.geocode_city", new=AsyncMock(return_value=_fake_geocode())):
            result = await find_workation_venues("Bengaluru")

        assert result.total_venues_found == 4
        assert result.venues_with_verified_wifi_count == 1
        assert result.has_limited_coverage is True
        # The verified-wifi venue should still be surfaced, ranked first.
        assert result.venues[0].name == "Cafe D (verified)"
        assert result.venues[0].has_verified_wifi is True

    @pytest.mark.asyncio
    async def test_good_coverage_is_not_flagged_as_limited(self):
        elements = [
            _make_element(i, f"Cafe {i}", {"amenity": "cafe", "internet_access": "wlan"})
            for i in range(5)
        ]
        client = _mock_client(_make_response(elements))
        with patch("services.workation_venues.httpx.AsyncClient", return_value=client), \
             patch("services.workation_venues.geocode_city", new=AsyncMock(return_value=_fake_geocode())):
            result = await find_workation_venues("Bengaluru")

        assert result.has_limited_coverage is False
        assert result.venues_with_verified_wifi_count == 5

    @pytest.mark.asyncio
    async def test_empty_overpass_result_is_limited_coverage_with_no_venues(self):
        client = _mock_client(_make_response([]))
        with patch("services.workation_venues.httpx.AsyncClient", return_value=client), \
             patch("services.workation_venues.geocode_city", new=AsyncMock(return_value=_fake_geocode())):
            result = await find_workation_venues("Tiny Village")

        assert result.venues == []
        assert result.total_venues_found == 0
        assert result.has_limited_coverage is True

    @pytest.mark.asyncio
    async def test_network_failure_returns_limited_coverage_not_an_exception(self):
        client = AsyncMock()
        client.post = AsyncMock(side_effect=Exception("connection reset"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("services.workation_venues.httpx.AsyncClient", return_value=client), \
             patch("services.workation_venues.geocode_city", new=AsyncMock(return_value=_fake_geocode())), \
             patch("services.workation_venues.asyncio.sleep", new=AsyncMock()):
            result = await find_workation_venues("Bengaluru")

        assert result.venues == []
        assert result.has_limited_coverage is True

    @pytest.mark.asyncio
    async def test_limit_truncates_returned_venues(self):
        elements = [
            _make_element(i, f"Cafe {i}", {"amenity": "cafe", "internet_access": "wlan"})
            for i in range(20)
        ]
        client = _mock_client(_make_response(elements))
        with patch("services.workation_venues.httpx.AsyncClient", return_value=client), \
             patch("services.workation_venues.geocode_city", new=AsyncMock(return_value=_fake_geocode())):
            result = await find_workation_venues("Bengaluru", limit=5)

        assert len(result.venues) == 5
        assert result.total_venues_found == 20
