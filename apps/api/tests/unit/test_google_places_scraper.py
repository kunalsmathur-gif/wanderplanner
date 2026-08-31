"""Tests for scrapers/google_places.py — the Google Places POI trial
provider (core/config.py's "Google Places POI trial" block).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.common import GeocodeResponse
from scrapers.google_places import (
    FIELD_MASK,
    GooglePlacesQuotaError,
    _poi_from_place,
    estimate_cost_usd,
    fetch_google_places_pois,
    poi_point_id,
)


def _place(name: str, types: list[str], lat: float = 15.29, lon: float = 74.12,
           rating: float | None = 4.5, rating_count: int | None = 100, place_id: str = "abc123") -> dict:
    return {
        "id": place_id,
        "displayName": {"text": name, "languageCode": "en"},
        "location": {"latitude": lat, "longitude": lon},
        "types": types,
        "rating": rating,
        "userRatingCount": rating_count,
    }


def _geo() -> GeocodeResponse:
    return GeocodeResponse(display_name="Goa, India", lat=15.2993, lon=74.1240, country_code="in")


class TestFieldMaskStaysOnProSku:
    def test_does_not_request_enterprise_sku_fields(self):
        """FIELD_MASK must never request `rating`/`userRatingCount` (or any
        other Enterprise-SKU field) — architecture decision 2026-08-31:
        Nearby Search bills the WHOLE request at the highest-tier field
        present, so requesting even one Enterprise field would move every
        call from the Pro rate ($9.60/1000, 35,000/month free in India) to
        the pricier Enterprise rate ($10.50/1000, only 7,000/month free)."""
        requested_fields = {f.strip() for f in FIELD_MASK.split(",")}
        enterprise_sku_fields = {
            "places.rating", "places.userRatingCount", "places.currentOpeningHours",
            "places.regularOpeningHours", "places.nationalPhoneNumber",
            "places.internationalPhoneNumber", "places.priceLevel", "places.websiteUri",
        }
        assert requested_fields.isdisjoint(enterprise_sku_fields)

    def test_requests_the_expected_pro_sku_fields(self):
        requested_fields = {f.strip() for f in FIELD_MASK.split(",")}
        assert requested_fields == {"places.id", "places.displayName", "places.location", "places.types"}


class TestPoiFromPlace:
    def test_builds_a_valid_payload_with_expected_attraction_type(self):
        poi = _poi_from_place(_place("Flora Restaurant", ["restaurant", "food"]), "Goa", "food_drink")
        assert poi is not None
        assert poi["name"] == "Flora Restaurant"
        assert poi["attraction_type"] == "restaurant"
        assert poi["lat"] == 15.29
        assert poi["lon"] == 74.12
        assert poi["source"] == "google_places"
        assert poi["google_place_id"] == "abc123"
        assert "Rated 4.5/5" in poi["text"]

    def test_maps_landmark_types_to_landmark_attraction_type(self):
        poi = _poi_from_place(_place("Red Fort", ["historical_landmark", "tourist_attraction"]), "Delhi", "landmark")
        assert poi["attraction_type"] == "landmark"
        assert poi["poi_type"] == "historical_landmark"

    def test_unknown_type_falls_back_to_activity(self):
        poi = _poi_from_place(_place("Mystery Place", ["some_new_google_type"]), "Delhi", "landmark")
        assert poi["attraction_type"] == "activity"

    def test_missing_name_returns_none(self):
        place = _place("", ["restaurant"])
        assert _poi_from_place(place, "Goa", "food_drink") is None

    def test_missing_location_returns_none(self):
        place = _place("Some Cafe", ["cafe"])
        place["location"] = {}
        assert _poi_from_place(place, "Goa", "food_drink") is None

    def test_omits_rating_sentence_when_no_reviews(self):
        poi = _poi_from_place(
            _place("New Place", ["restaurant"], rating=None, rating_count=None), "Goa", "food_drink",
        )
        assert "Rated" not in poi["text"]


class TestEstimateCostUsd:
    def test_zero_calls_is_zero_cost(self):
        assert estimate_cost_usd(0) == 0.0

    def test_1000_calls_matches_configured_rate(self):
        from core.config import settings
        assert estimate_cost_usd(1000) == pytest.approx(settings.google_places_cost_per_1000_calls_usd)


class TestPoiPointId:
    def test_same_destination_and_name_produces_same_id(self):
        assert poi_point_id("Goa", "Flora Restaurant") == poi_point_id("Goa", "Flora Restaurant")

    def test_different_names_produce_different_ids(self):
        assert poi_point_id("Goa", "Flora Restaurant") != poi_point_id("Goa", "Girish Restaurant")

    def test_matches_osm_scheme_for_the_same_destination_and_name(self):
        """Deliberately duplicates scrapers/osm.py's hashing so a destination
        re-ingested by the OTHER provider next week overwrites the same
        points instead of accumulating duplicates."""
        import hashlib
        expected = int(hashlib.md5("Goa::Flora Restaurant".encode()).hexdigest(), 16) % (2**63)
        assert poi_point_id("Goa", "Flora Restaurant") == expected


@pytest.mark.asyncio
class TestFetchGooglePlacesPois:
    async def test_raises_quota_error_when_no_api_key_configured(self):
        with patch("scrapers.google_places.settings") as mock_settings:
            mock_settings.google_places_enabled = True
            mock_settings.google_places_api_key = ""
            with pytest.raises(GooglePlacesQuotaError, match="No Google Places API key"):
                await fetch_google_places_pois("Goa")

    async def test_raises_quota_error_when_disabled(self):
        with patch("scrapers.google_places.settings") as mock_settings:
            mock_settings.google_places_enabled = False
            with pytest.raises(GooglePlacesQuotaError, match="disabled"):
                await fetch_google_places_pois("Goa")

    async def test_aggregates_pois_across_category_groups_and_dedupes_by_name(self):
        responses_by_call = [
            {"places": [_place("Red Fort", ["historical_landmark"])]},
            {"places": [_place("City Museum", ["museum"])]},
            {"places": [_place("Central Park", ["park"])]},
            {"places": [_place("Cinema Hall", ["movie_theater"])]},
            # Duplicate name across two category calls (e.g. tourist_attraction
            # showing up in both landmark and entertainment groups) must dedupe.
            {"places": [_place("Red Fort", ["tourist_attraction"]), _place("Flora Restaurant", ["restaurant"])]},
        ]

        call_index = {"n": 0}

        async def fake_post(*args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = responses_by_call[call_index["n"]]
            call_index["n"] += 1
            return resp

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("scrapers.google_places.settings") as mock_settings, \
             patch("scrapers.google_places.geocode_city", new=AsyncMock(return_value=_geo())), \
             patch("scrapers.google_places.httpx.AsyncClient", return_value=mock_client):
            mock_settings.google_places_enabled = True
            mock_settings.google_places_api_key = "fake-key"
            mock_settings.google_places_max_results_per_category = 20
            mock_settings.osm_poi_radius_m = 5000

            pois, call_count = await fetch_google_places_pois("Goa")

        assert call_count == 5  # one per category group
        names = {p["name"] for p in pois}
        assert names == {"Red Fort", "City Museum", "Central Park", "Cinema Hall", "Flora Restaurant"}

    async def test_403_raises_quota_error_and_stops_remaining_category_calls(self):
        resp = MagicMock()
        resp.status_code = 403
        resp.text = "blocked"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("scrapers.google_places.settings") as mock_settings, \
             patch("scrapers.google_places.geocode_city", new=AsyncMock(return_value=_geo())), \
             patch("scrapers.google_places.httpx.AsyncClient", return_value=mock_client):
            mock_settings.google_places_enabled = True
            mock_settings.google_places_api_key = "fake-key"
            mock_settings.google_places_max_results_per_category = 20
            mock_settings.osm_poi_radius_m = 5000

            with pytest.raises(GooglePlacesQuotaError):
                await fetch_google_places_pois("Goa")

        # Only the first category group's call should have been attempted —
        # a blocked key fails identically on every subsequent call.
        assert mock_client.post.await_count == 1

    async def test_one_failed_category_does_not_sink_the_whole_destination(self):
        good_resp = MagicMock()
        good_resp.status_code = 200
        good_resp.raise_for_status = MagicMock()
        good_resp.json.return_value = {"places": [_place("Red Fort", ["historical_landmark"])]}

        async def fake_post(*args, **kwargs):
            if fake_post.calls == 0:
                fake_post.calls += 1
                raise ConnectionError("transient network blip")
            fake_post.calls += 1
            return good_resp
        fake_post.calls = 0

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("scrapers.google_places.settings") as mock_settings, \
             patch("scrapers.google_places.geocode_city", new=AsyncMock(return_value=_geo())), \
             patch("scrapers.google_places.httpx.AsyncClient", return_value=mock_client):
            mock_settings.google_places_enabled = True
            mock_settings.google_places_api_key = "fake-key"
            mock_settings.google_places_max_results_per_category = 20
            mock_settings.osm_poi_radius_m = 5000

            pois, call_count = await fetch_google_places_pois("Goa")

        assert call_count == 5
        assert len(pois) >= 1  # the categories after the failed one still contributed
