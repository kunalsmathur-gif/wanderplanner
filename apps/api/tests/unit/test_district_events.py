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
    _DISTRICT_MAX_EVENTS_PER_CITY,
    _district_item_to_record,
    _parse_discovery_results,
    fetch_district_events,
    fetch_district_events_batch,
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
            for i in range(_DISTRICT_MAX_EVENTS_PER_CITY + 50)
        ]
        data = {"EDSResponse": {"rails": [{"items": items}]}}
        records = _parse_discovery_results(data, fallback_city="Mumbai")
        assert len(records) == _DISTRICT_MAX_EVENTS_PER_CITY

    def test_default_cap_is_generous_enough_to_span_multiple_rails(self):
        # Regression test for a real coverage gap found live (2026-10-06):
        # a single `get_discovery_results` response contains every rail
        # (Trending, Dandiya/Garba, Sports, Food, etc.) in one page load —
        # a low cap meant whichever rail came first (observed live: an
        # in-season Dandiya/Garba rail) silently consumed the whole budget
        # before the loop ever reached other rails, even though all of
        # that data was already sitting in the one response. Confirmed
        # live: 139 of 157 District.in-sourced events were "culture" versus
        # single digits for every other category. The cap must comfortably
        # exceed a single rail's typical item count (observed live: dozens
        # of items in a season-driven rail) so other rails aren't starved.
        first_rail_items = [
            {"ItemDetails": {"EventData": {"name": f"Dandiya Night {i}", "start_time_epoch": 1792000000}}}
            for i in range(30)  # more than the old cap (20), well under the new one
        ]
        second_rail_items = [
            {"ItemDetails": {"EventData": {"name": "ISL Match: Bengaluru FC", "start_time_epoch": 1792000000}}}
        ]
        data = {
            "EDSResponse": {
                "rails": [
                    {"items": first_rail_items},
                    {"items": second_rail_items},
                ]
            }
        }
        records = _parse_discovery_results(data, fallback_city="Bengaluru")
        names = [r.name for r in records]
        assert "ISL Match: Bengaluru FC" in names


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


class TestDistrictCityCoords:
    def test_covers_every_city_in_the_ingest_default_sweep(self):
        """Every city `ingest_india_events()` sweeps by default must have a
        seed coordinate here, or District.in silently contributes zero
        events for it regardless of real coverage (the exact class of
        coverage gap the per-city caps fixed earlier this session, but at
        the city-list level instead of the per-city-cap level)."""
        from scrapers.india_events import _INGEST_DEFAULT_CITIES

        missing = [c for c in _INGEST_DEFAULT_CITIES if c not in _DISTRICT_CITY_COORDS]
        assert missing == []

    def test_has_more_than_the_original_seven_metros(self):
        assert len(_DISTRICT_CITY_COORDS) > 7


class TestFetchDistrictEventsBatch:
    @pytest.mark.asyncio
    async def test_missing_playwright_degrades_every_city_to_empty(self):
        with patch.dict("sys.modules", {"playwright.async_api": None}):
            results = await fetch_district_events_batch(["Mumbai", "Delhi"])

        assert results == {"Mumbai": [], "Delhi": []}

    @pytest.mark.asyncio
    async def test_shares_one_browser_launch_across_all_cities(self):
        """The whole point of the batch helper: one `chromium.launch()`
        call regardless of how many cities are requested, not one per
        city (that per-city-browser cost is what made sweeping 58 cities
        instead of 7 expensive before this change)."""
        from unittest.mock import AsyncMock, MagicMock

        mock_browser = MagicMock()
        mock_browser.close = AsyncMock()
        mock_context = MagicMock()
        mock_context.close = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_page = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_page.on = MagicMock()
        mock_page.goto = AsyncMock(side_effect=TimeoutError("no response captured"))

        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)
        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium = mock_chromium
        mock_pw_cm = MagicMock()
        mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw_cm.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "playwright.async_api.async_playwright", return_value=mock_pw_cm
        ):
            results = await fetch_district_events_batch(
                ["Mumbai", "Delhi", "Pune"], max_concurrent=2
            )

        mock_chromium.launch.assert_called_once()
        assert set(results.keys()) == {"Mumbai", "Delhi", "Pune"}
        assert all(v == [] for v in results.values())

    @pytest.mark.asyncio
    async def test_browser_launch_failure_degrades_to_empty_not_raises(self):
        """Regression test for a real bug found live (2026-10-06): a
        Chromium launch failure (e.g. local resource contention/timeout)
        previously propagated uncaught out of this function. Since
        `ingest_india_events()` now runs this batch concurrently with the
        HTTP-based tiers via `asyncio.gather`, an uncaught exception here
        would have taken down the *other* tier's already-fetched results
        too — must degrade to `[]` per city instead, like every other
        fetcher's best-effort contract."""
        from unittest.mock import AsyncMock, MagicMock

        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(side_effect=TimeoutError("launch timed out"))
        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium = mock_chromium
        mock_pw_cm = MagicMock()
        mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("playwright.async_api.async_playwright", return_value=mock_pw_cm):
            results = await fetch_district_events_batch(["Mumbai", "Delhi"])

        assert results == {"Mumbai": [], "Delhi": []}

