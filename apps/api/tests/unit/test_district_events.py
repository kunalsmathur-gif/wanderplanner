"""Unit tests for scrapers/district_events.py.

Only the pure parsing functions (`_parse_discovery_results`,
`_district_item_to_record`) and the no-Playwright/unknown-city degrade
paths of `fetch_district_events()` are tested here — actually launching a
headless Chromium instance is exercised via manual/live verification (see
this session's history), not in the unit suite, to keep tests fast and
fully offline.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from scrapers.district_events import (
    _DISTRICT_CITY_COORDS,
    _district_item_to_record,
    _parse_discovery_results,
    fetch_district_events,
)


class TestDistrictItemToRecord:
    def test_maps_full_item(self):
        item = {
            "event_id": "abc123",
            "name": "Bollywood Music Project",
            "start_time_epoch": 1792000000,
            "end_time_epoch": 1792010000,
            "city": "Mumbai",
            "tags": ["music", ""],
            "event_slug": "bollywood-music-project-2026",
        }
        record = _district_item_to_record(item, fallback_city="Mumbai")

        assert record is not None
        assert record.name == "Bollywood Music Project"
        assert record.location == "Mumbai"
        assert record.source_citation == "District.in (headless render)"
        assert record.deep_link == "https://www.district.in/events/bollywood-music-project-2026"
        assert record.interest_category == "music"

    def test_missing_end_epoch_falls_back_to_start(self):
        item = {
            "name": "One-Off Show",
            "start_time_epoch": 1792000000,
            "city": "Delhi",
        }
        record = _district_item_to_record(item, fallback_city="Delhi")
        assert record is not None
        assert record.start_date == record.end_date

    def test_missing_city_falls_back_to_caller_city(self):
        item = {"name": "No City Event", "start_time_epoch": 1792000000}
        record = _district_item_to_record(item, fallback_city="Pune")
        assert record is not None
        assert record.location == "Pune"

    def test_missing_name_returns_none(self):
        item = {"start_time_epoch": 1792000000}
        assert _district_item_to_record(item, fallback_city="Pune") is None

    def test_missing_start_epoch_returns_none(self):
        item = {"name": "No Date Event"}
        assert _district_item_to_record(item, fallback_city="Pune") is None

    def test_no_slug_leaves_deep_link_none(self):
        item = {"name": "Unlinked Event", "start_time_epoch": 1792000000, "city": "Pune"}
        record = _district_item_to_record(item, fallback_city="Pune")
        assert record is not None
        assert record.deep_link is None


class TestParseDiscoveryResults:
    def test_parses_nested_rails_and_items(self):
        data = {
            "EDSResponse": {
                "rails": [
                    {
                        "items": [
                            {
                                "ItemDetails": {
                                    "EventData": {
                                        "name": "Rail Event",
                                        "start_time_epoch": 1792000000,
                                        "city": "Chennai",
                                    }
                                }
                            },
                            # Non-event item (e.g. a movie/dining card) must
                            # be skipped, not crash the whole rail.
                            {"ItemDetails": {"MovieData": {"name": "Some Movie"}}},
                        ]
                    }
                ]
            }
        }
        records = _parse_discovery_results(data, fallback_city="Chennai")
        assert len(records) == 1
        assert records[0].name == "Rail Event"

    def test_empty_response_returns_empty(self):
        assert _parse_discovery_results({}, fallback_city="Mumbai") == []

    def test_caps_at_max_events_per_city(self):
        items = [
            {"ItemDetails": {"EventData": {"name": f"Event {i}", "start_time_epoch": 1792000000}}}
            for i in range(50)
        ]
        data = {"EDSResponse": {"rails": [{"items": items}]}}
        records = _parse_discovery_results(data, fallback_city="Mumbai")
        assert len(records) == 20  # _DISTRICT_MAX_EVENTS_PER_CITY


class TestFetchDistrictEventsDegradation:
    @pytest.mark.asyncio
    async def test_unknown_city_returns_empty_without_launching_browser(self):
        assert "Atlantis" not in _DISTRICT_CITY_COORDS
        with patch("playwright.async_api.async_playwright") as mock_pw:
            records = await fetch_district_events("Atlantis")

        assert records == []
        mock_pw.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_playwright_degrades_to_empty(self):
        with patch.dict("sys.modules", {"playwright.async_api": None}):
            records = await fetch_district_events("Mumbai")

        assert records == []
