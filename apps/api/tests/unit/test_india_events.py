"""Unit tests for scrapers/india_events.py (docs/plans/india-workation-finder-plan.md).

No API keys are available in this environment, so every primary-tier test
mocks httpx — fully offline, same pattern as tests/unit/test_youtube_comments.py
and tests/unit/test_osm_scraper.py.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from scrapers.india_events import (
    _CURATED_EVENTS,
    EventRecord,
    _parse_event_date_range,
    _parse_event_location,
    curated_tier_a_events,
    embed_and_store_india_events,
    fetch_allevents,
    fetch_bandsintown,
    fetch_eventbrite,
    ingest_india_events,
    scrape_wikipedia_festivals,
)


def _mock_response(json_data: dict | list, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


class TestEventRecordValidation:
    def test_valid_record_constructs(self):
        record = EventRecord(
            name="Pushkar Mela",
            start_date=date(2025, 10, 28),
            end_date=date(2025, 11, 5),
            location="Pushkar, Rajasthan",
            interest_category="culture",
            source_citation="Rajasthan Tourism",
        )
        assert record.deep_link is None
        assert record.interest_category == "culture"

    def test_invalid_interest_category_rejected(self):
        with pytest.raises(ValidationError):
            EventRecord(
                name="Mystery Event",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 1, 2),
                location="Delhi",
                interest_category="not-a-real-category",
                source_citation="nowhere",
            )

    def test_missing_required_field_rejected(self):
        with pytest.raises(ValidationError):
            EventRecord(
                name="Missing Citation",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 1, 2),
                location="Delhi",
                interest_category="music",
            )


class TestGracefulNoOpWithoutKeys:
    @pytest.mark.asyncio
    async def test_allevents_no_key_returns_empty_without_request(self):
        with patch("scrapers.india_events.settings.allevents_api_key", None), \
             patch("scrapers.india_events.httpx.AsyncClient") as mock_client_cls:
            records = await fetch_allevents("Mumbai")

        assert records == []
        mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_eventbrite_no_key_returns_empty_without_request(self):
        with patch("scrapers.india_events.settings.eventbrite_api_key", None), \
             patch("scrapers.india_events.httpx.AsyncClient") as mock_client_cls:
            records = await fetch_eventbrite("Delhi")

        assert records == []
        mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_bandsintown_no_key_returns_empty_without_request(self):
        with patch("scrapers.india_events.settings.bandsintown_app_id", None), \
             patch("scrapers.india_events.httpx.AsyncClient") as mock_client_cls:
            records = await fetch_bandsintown("some-artist")

        assert records == []
        mock_client_cls.assert_not_called()


class TestPrimaryTierParsing:
    @pytest.mark.asyncio
    async def test_allevents_parses_response_into_records(self):
        payload = {
            "data": [
                {
                    "title": "Sunburn Festival",
                    "start_time": "2025-12-28T18:00:00",
                    "end_time": "2025-12-30T23:00:00",
                    "venue": {"city": "Goa"},
                    "category": "music festival",
                    "event_url": "https://allevents.in/goa/sunburn",
                },
                # Malformed item (no title) should be skipped, not crash.
                {"start_time": "2025-12-28T18:00:00"},
            ]
        }
        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get.return_value = _mock_response(payload)

        with patch("scrapers.india_events.settings.allevents_api_key", "fake-key"), \
             patch("scrapers.india_events.httpx.AsyncClient", return_value=mock_client):
            records = await fetch_allevents("Goa")

        assert len(records) == 1
        assert records[0].name == "Sunburn Festival"
        assert records[0].interest_category == "music"
        assert records[0].location == "Goa"
        assert records[0].source_citation == "AllEvents.in API"

    @pytest.mark.asyncio
    async def test_allevents_rate_limited_returns_empty_without_retry(self):
        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get.return_value = _mock_response({}, status_code=429)

        with patch("scrapers.india_events.settings.allevents_api_key", "fake-key"), \
             patch("scrapers.india_events.httpx.AsyncClient", return_value=mock_client):
            records = await fetch_allevents("Mumbai")

        assert records == []
        # Only called once -- a 429 is terminal, not retried.
        assert mock_client.__aenter__.return_value.get.call_count == 1


class TestCuratedTierA:
    def test_curated_dataset_is_nonempty(self):
        assert len(_CURATED_EVENTS) > 0

    def test_curated_events_validate_as_event_records(self):
        records = curated_tier_a_events()
        assert len(records) == len(_CURATED_EVENTS)
        for record in records:
            assert isinstance(record, EventRecord)
            assert record.source_citation  # every curated entry must cite a source
            assert record.end_date >= record.start_date

    def test_curated_dataset_covers_expected_categories(self):
        records = curated_tier_a_events()
        categories = {r.interest_category for r in records}
        assert "pilgrimage" in categories
        assert "sports" in categories
        assert "culture" in categories


class TestIngestDedup:
    @pytest.mark.asyncio
    async def test_dedupes_identical_events_across_tiers(self):
        duplicate = EventRecord(
            name="Pushkar Mela",
            start_date=date(2026, 11, 20),
            end_date=date(2026, 11, 24),
            location="Pushkar, Rajasthan",
            interest_category="culture",
            source_citation="AllEvents.in API",
        )

        async def _fake_allevents(city):
            return [duplicate] if city == "Mumbai" else []

        with patch("scrapers.india_events.fetch_allevents", side_effect=_fake_allevents), \
             patch("scrapers.india_events.fetch_eventbrite", return_value=[]), \
             patch("scrapers.india_events.scrape_wikipedia_festivals", return_value=[]):
            events = await ingest_india_events(cities=["Mumbai"])

        # The curated Tier A dataset already contains a "Pushkar Mela" entry
        # with the exact same dates/location -- the API-sourced duplicate
        # must collapse into it, not double up.
        matching = [e for e in events if e.name.lower() == "pushkar mela"]
        assert len(matching) == 1

    @pytest.mark.asyncio
    async def test_distinct_events_are_all_kept(self):
        with patch("scrapers.india_events.fetch_allevents", return_value=[]), \
             patch("scrapers.india_events.fetch_eventbrite", return_value=[]), \
             patch("scrapers.india_events.scrape_wikipedia_festivals", return_value=[]):
            events = await ingest_india_events(cities=["Mumbai"])

        # At minimum, every curated entry should survive untouched.
        assert len(events) >= len(_CURATED_EVENTS)
        names = {e.name for e in events}
        assert "Char Dham Yatra (opening)" in names
        assert "Rath Yatra (Puri)" in names


class TestEmbedAndStore:
    def test_empty_list_short_circuits_without_embedding(self):
        with patch("scrapers.india_events.embed") as mock_embed, \
             patch("scrapers.india_events.get_qdrant") as mock_get_qdrant:
            count = embed_and_store_india_events([])

        assert count == 0
        mock_embed.assert_not_called()
        mock_get_qdrant.assert_not_called()

    def test_upserts_one_point_per_event(self):
        records = curated_tier_a_events()[:2]
        mock_client = MagicMock()

        with patch("scrapers.india_events.embed", return_value=[[0.1] * 384 for _ in records]), \
             patch("scrapers.india_events.get_qdrant", return_value=mock_client):
            count = embed_and_store_india_events(records)

        assert count == len(records)
        mock_client.upsert.assert_called_once()
        _, kwargs = mock_client.upsert.call_args
        assert len(kwargs["points"]) == len(records)
        payload = kwargs["points"][0].payload
        assert payload["name"] == records[0].name
        assert payload["source_citation"] == records[0].source_citation


class TestWikipediaDateParsing:
    """Unit coverage for `_parse_event_date_range()`'s regex heuristics,
    using realistic Wikipedia-intro-style sentences (Hampi Utsav/Pushkar
    Mela/Durga Puja-shaped text) rather than synthetic fixtures."""

    def test_explicit_cross_month_range_with_year_is_parsed(self):
        # Pushkar-Mela-style: "Month D to Month D, Year".
        year = date.today().year + 1
        text = (
            f"Pushkar Mela is a multi-day camel and livestock fair held every "
            f"year in Pushkar, Rajasthan. This year's fair runs from "
            f"October 28 to November 5, {year}."
        )
        result = _parse_event_date_range(text)
        assert result == (date(year, 10, 28), date(year, 11, 5))

    def test_explicit_same_month_range_with_year_is_parsed(self):
        # Hampi-Utsav-style: "D to D Month Year".
        year = date.today().year + 1
        text = (
            f"Hampi Utsav is a cultural festival celebrated annually in "
            f"Hampi, Karnataka, showcasing music and dance. It is held "
            f"from 3 to 5 January {year} this edition."
        )
        result = _parse_event_date_range(text)
        assert result == (date(year, 1, 3), date(year, 1, 5))

    def test_month_only_range_without_year_resolves_to_upcoming_occurrence(self):
        # Durga-Puja-style: "(Month–Month)" parenthetical, no explicit year.
        text = (
            "Durga Puja is observed in the Indian calendar in the month of "
            "Ashvin (September-October) on the Hindu luni-solar calendar."
        )
        result = _parse_event_date_range(text)
        assert result is not None
        start, end = result
        assert (start.month, start.day) == (9, 1)
        assert end.month == 10
        assert start >= date.today() or start.year >= date.today().year

    def test_plain_day_month_with_recurrence_keyword_resolves_year(self):
        text = (
            "Shiv Jayanti is celebrated on February 19, marking the birth "
            "anniversary of Chhatrapati Shivaji Maharaj. The state government "
            "started the widespread annual Shivjayanti celebrations."
        )
        result = _parse_event_date_range(text)
        assert result is not None
        start, end = result
        assert start == end
        assert (start.month, start.day) == (2, 19)
        assert start >= date.today()

    def test_stale_historical_year_is_not_used_as_the_event_date(self):
        # Birth-year-style false positive: a centuries-old date mention must
        # not be mistaken for the event's (recurring) date, and a recent,
        # recurrence-flagged month+day mentioned earlier in the same text
        # must be preferred instead.
        text = (
            "Shiv Jayanti is celebrated on February 19 every year. "
            "Historical records give the corresponding date as 19th Feb 1630."
        )
        result = _parse_event_date_range(text)
        assert result is not None
        start, _end = result
        assert start.year >= date.today().year - 1
        assert start.year != 1630

    def test_no_reliable_date_returns_none(self):
        text = (
            "This is a general-interest article about a cultural practice "
            "with no specific recurring schedule mentioned anywhere in it."
        )
        assert _parse_event_date_range(text) is None


class TestWikipediaLocationParsing:
    def test_city_state_pair_is_preferred(self):
        text = "The fair is held annually in Pushkar, Rajasthan, drawing visitors from across India."
        assert _parse_event_location(text) == "Pushkar, Rajasthan"

    def test_city_comma_india_is_recognized(self):
        text = "The marathon is held in Mumbai, India, on the third Sunday of January every year."
        assert _parse_event_location(text) == "Mumbai, India"

    def test_bare_state_name_is_recognized_as_fallback(self):
        text = "The festival is celebrated in the Northeastern Indian state of Assam every year."
        assert _parse_event_location(text) == "Assam"

    def test_no_recognizable_indian_location_returns_none(self):
        text = "The festival is celebrated somewhere in the region every year."
        assert _parse_event_location(text) is None


class TestScrapeWikipediaFestivalsIntegration:
    """End-to-end: mocks the MediaWiki category-walk + batched-extracts HTTP
    calls and asserts the real parsing/skip/category-mapping logic wired
    together in `scrape_wikipedia_festivals()`."""

    def _mock_wiki_client(self, categories: dict, extracts: dict):
        def _get(url, params=None, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if params.get("list") == "categorymembers":
                members = categories.get(params["cmtitle"], [])
                resp.json.return_value = {
                    "query": {"categorymembers": [{"title": t} for t in members]}
                }
            else:
                titles = params["titles"].split("|")
                pages = {
                    str(i): {"title": t, "extract": extracts.get(t, "")}
                    for i, t in enumerate(titles)
                }
                resp.json.return_value = {"query": {"pages": pages}}
            return resp

        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.side_effect = _get
        return mock_client

    def test_sports_category_member_forced_to_sports(self):
        year = date.today().year + 1
        categories = {
            "Category:Festivals in India": [],
            "Category:Annual sporting events in India": ["Jaipur Marathon"],
        }
        extracts = {
            "Jaipur Marathon": (
                f"The Jaipur Marathon is an annual international marathon held "
                f"in Jaipur, Rajasthan. This year's race is on 15 February {year}."
            ),
        }
        mock_client = self._mock_wiki_client(categories, extracts)

        with patch("scrapers.india_events.httpx.Client", return_value=mock_client), \
             patch("scrapers.india_events.time.sleep"):
            records = scrape_wikipedia_festivals()

        assert len(records) == 1
        record = records[0]
        assert record.name == "Jaipur Marathon"
        assert record.interest_category == "sports"
        assert record.location == "Jaipur, Rajasthan"
        assert record.start_date == date(year, 2, 15)
        assert record.source_citation == "https://en.wikipedia.org/wiki/Jaipur_Marathon"
        assert record.deep_link == record.source_citation

    def test_festival_category_member_classified_via_keyword_heuristic(self):
        year = date.today().year + 1
        categories = {
            "Category:Festivals in India": ["Konark Dance Festival"],
            "Category:Annual sporting events in India": [],
        }
        extracts = {
            "Konark Dance Festival": (
                f"Konark Dance Festival is an annual classical music and dance "
                f"festival held in Konark, Odisha, from 1 to 5 December {year}."
            ),
        }
        mock_client = self._mock_wiki_client(categories, extracts)

        with patch("scrapers.india_events.httpx.Client", return_value=mock_client), \
             patch("scrapers.india_events.time.sleep"):
            records = scrape_wikipedia_festivals()

        assert len(records) == 1
        record = records[0]
        assert record.interest_category == "music"
        assert record.location == "Konark, Odisha"
        assert record.start_date == date(year, 12, 1)
        assert record.end_date == date(year, 12, 5)

    def test_page_with_no_reliable_date_or_location_is_skipped_not_fabricated(self):
        categories = {
            "Category:Festivals in India": ["Vague Festival"],
            "Category:Annual sporting events in India": [],
        }
        extracts = {
            "Vague Festival": (
                "Vague Festival is a local celebration with cultural significance, "
                "but no widely documented recurring schedule or venue."
            ),
        }
        mock_client = self._mock_wiki_client(categories, extracts)

        with patch("scrapers.india_events.httpx.Client", return_value=mock_client), \
             patch("scrapers.india_events.time.sleep"):
            records = scrape_wikipedia_festivals()

        assert records == []

    def test_page_with_missing_extract_is_skipped(self):
        categories = {
            "Category:Festivals in India": ["Redirect Only Stub"],
            "Category:Annual sporting events in India": [],
        }
        mock_client = self._mock_wiki_client(categories, extracts={})

        with patch("scrapers.india_events.httpx.Client", return_value=mock_client), \
             patch("scrapers.india_events.time.sleep"):
            records = scrape_wikipedia_festivals()

        assert records == []

    def test_category_walk_failure_returns_empty_list_not_raises(self):
        with patch("scrapers.india_events.httpx.Client", side_effect=Exception("boom")):
            records = scrape_wikipedia_festivals()

        assert records == []

    @pytest.mark.asyncio
    async def test_wired_into_ingest_india_events_and_deduped(self):
        year = date.today().year + 1
        wiki_record = EventRecord(
            name="Konark Dance Festival",
            start_date=date(year, 12, 1),
            end_date=date(year, 12, 5),
            location="Konark, Odisha",
            interest_category="music",
            source_citation="https://en.wikipedia.org/wiki/Konark_Dance_Festival",
        )

        with patch("scrapers.india_events.fetch_allevents", return_value=[]), \
             patch("scrapers.india_events.fetch_eventbrite", return_value=[]), \
             patch("scrapers.india_events.scrape_wikipedia_festivals", return_value=[wiki_record]):
            events = await ingest_india_events(cities=["Mumbai"])

        # The Tier B record must actually be merged into the final result
        # (not dropped), proving `ingest_india_events()` really invokes
        # `scrape_wikipedia_festivals()` in its normal orchestration path.
        names = {e.name for e in events}
        assert "Konark Dance Festival" in names
