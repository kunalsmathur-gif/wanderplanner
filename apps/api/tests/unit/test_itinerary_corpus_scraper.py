"""
Unit tests for scrapers/itinerary_corpus.py (docs/rag-strategy.md §9, Phase v0).

All tests are fully offline — httpx, feedparser, and youtube_transcript_api
calls are mocked. This module only fetches RAW content; it does not embed or
write to Qdrant, so no vector-store mocking is needed here.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scrapers.itinerary_corpus import (
    _is_itinerary_shaped,
    scrape_travel_blog_feed,
    scrape_wikivoyage_itinerary,
    scrape_reddit_trip_reports,
    fetch_youtube_transcript,
    collect_itinerary_corpus_raw,
)


class TestIsItineraryShaped:
    def test_matches_day_count_title(self):
        assert _is_itinerary_shaped("The Perfect 7 Day Itinerary for Kyoto")

    def test_matches_week_count_title(self):
        assert _is_itinerary_shaped("Two Weeks in Vietnam: A Trip Report")

    def test_matches_bare_itinerary_keyword(self):
        assert _is_itinerary_shaped("My Bali Itinerary")

    def test_rejects_generic_listicle_title(self):
        assert not _is_itinerary_shaped("10 Best Restaurants in Paris")

    def test_rejects_empty_title(self):
        assert not _is_itinerary_shaped("")


class TestScrapeTravelBlogFeed:
    @pytest.mark.asyncio
    async def test_filters_non_itinerary_entries(self):
        fake_feed = MagicMock()
        fake_feed.entries = [
            {"title": "10 Best Cafes in Rome", "link": "https://example.com/cafes", "summary": "not itinerary shaped"},
            {"title": "5 Day Rome Itinerary", "link": "https://example.com/rome-5-day", "summary": "short"},
        ]
        with patch("scrapers.itinerary_corpus.feedparser.parse", return_value=fake_feed), \
             patch("scrapers.itinerary_corpus._fetch_blog_post_body", new=AsyncMock(return_value="A" * 300)):
            docs = await scrape_travel_blog_feed({"name": "Test Blog", "url": "https://example.com/feed"})

        assert len(docs) == 1
        assert docs[0]["title"] == "5 Day Rome Itinerary"
        assert docs[0]["source"] == "travel_blog"
        assert docs[0]["source_name"] == "Test Blog"

    @pytest.mark.asyncio
    async def test_drops_short_body_below_threshold(self):
        fake_feed = MagicMock()
        fake_feed.entries = [
            {"title": "3 Day Itinerary for Goa", "link": "https://example.com/goa", "summary": "too short"},
        ]
        with patch("scrapers.itinerary_corpus.feedparser.parse", return_value=fake_feed), \
             patch("scrapers.itinerary_corpus._fetch_blog_post_body", new=AsyncMock(return_value="")):
            docs = await scrape_travel_blog_feed({"name": "Test Blog", "url": "https://example.com/feed"})

        assert docs == []

    @pytest.mark.asyncio
    async def test_feed_parse_failure_returns_empty(self):
        with patch("scrapers.itinerary_corpus.feedparser.parse", side_effect=Exception("network down")):
            docs = await scrape_travel_blog_feed({"name": "Test Blog", "url": "https://example.com/feed"})
        assert docs == []


class TestScrapeWikivoyageItinerary:
    @pytest.mark.asyncio
    async def test_parses_valid_response(self):
        html = "<p>" + ("Day one covers the old town and its historic sights. " * 10) + "</p>"
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "parse": {"title": "Golden Triangle (India)", "text": {"*": html}}
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.itinerary_corpus.httpx.AsyncClient", return_value=mock_client):
            doc = await scrape_wikivoyage_itinerary("Golden Triangle (India)")

        assert doc is not None
        assert doc["source"] == "wikivoyage_itinerary"
        assert "Golden_Triangle" in doc["source_url"]
        assert len(doc["raw_text"]) >= 200

    @pytest.mark.asyncio
    async def test_returns_none_on_api_error_field(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"error": {"code": "missingtitle"}}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.itinerary_corpus.httpx.AsyncClient", return_value=mock_client):
            doc = await scrape_wikivoyage_itinerary("Nonexistent Page")

        assert doc is None

    @pytest.mark.asyncio
    async def test_returns_none_on_network_failure(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.itinerary_corpus.httpx.AsyncClient", return_value=mock_client):
            doc = await scrape_wikivoyage_itinerary("Some Page")

        assert doc is None


class TestScrapeRedditTripReports:
    @pytest.mark.asyncio
    async def test_filters_by_title_shape_and_length_and_score(self):
        good_post = {
            "data": {
                "title": "My 10 Day Itinerary Through Japan",
                "selftext": "Day 1: arrived in Tokyo. " * 20,
                "score": 500,
                "permalink": "/r/travel/comments/abc123/my_10_day_itinerary/",
                "created_utc": 1700000000,
            }
        }
        low_score_post = {
            "data": {
                "title": "5 Day Itinerary for Rome",
                "selftext": "Day 1: arrived in Rome. " * 20,
                "score": 1,
                "permalink": "/r/travel/comments/def456/rome/",
                "created_utc": 1700000000,
            }
        }
        non_itinerary_post = {
            "data": {
                "title": "Is this hostel safe?",
                "selftext": "Asking for advice " * 20,
                "score": 500,
                "permalink": "/r/travel/comments/ghi789/hostel/",
                "created_utc": 1700000000,
            }
        }
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": {"children": [good_post, low_score_post, non_itinerary_post]}
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.itinerary_corpus.httpx.AsyncClient", return_value=mock_client), \
             patch("scrapers.itinerary_corpus.settings.reddit_min_score", 10):
            docs = await scrape_reddit_trip_reports()

        # good_post should appear once per subreddit searched (same mock response reused)
        titles = {d["title"] for d in docs}
        assert "My 10 Day Itinerary Through Japan" in titles
        assert "5 Day Itinerary for Rome" not in titles  # score too low
        assert "Is this hostel safe?" not in titles  # not itinerary-shaped

    @pytest.mark.asyncio
    async def test_network_failure_for_one_subreddit_does_not_crash(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("rate limited"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.itinerary_corpus.httpx.AsyncClient", return_value=mock_client):
            docs = await scrape_reddit_trip_reports()

        assert docs == []


class TestFetchYoutubeTranscript:
    @pytest.mark.asyncio
    async def test_returns_doc_for_valid_transcript(self):
        fake_snippet = MagicMock()
        fake_snippet.text = "Welcome to my ten day trip through India, starting in Delhi. " * 10

        fake_api_instance = MagicMock()
        fake_api_instance.fetch.return_value = [fake_snippet]
        fake_api_class = MagicMock(return_value=fake_api_instance)

        with patch("youtube_transcript_api.YouTubeTranscriptApi", fake_api_class):
            doc = await fetch_youtube_transcript("abc123", title="10 Days in India")

        assert doc is not None
        assert doc["source"] == "youtube_captions"
        assert doc["source_url"] == "https://www.youtube.com/watch?v=abc123"
        assert len(doc["raw_text"]) >= 200

    @pytest.mark.asyncio
    async def test_returns_none_on_fetch_failure(self):
        fake_api_instance = MagicMock()
        fake_api_instance.fetch.side_effect = Exception("no transcript available")
        fake_api_class = MagicMock(return_value=fake_api_instance)

        with patch("youtube_transcript_api.YouTubeTranscriptApi", fake_api_class):
            doc = await fetch_youtube_transcript("no_captions_video")

        assert doc is None


class TestCollectItineraryCorpusRaw:
    @pytest.mark.asyncio
    async def test_combines_all_sources_and_tolerates_partial_failure(self):
        with patch("scrapers.itinerary_corpus.scrape_all_travel_blogs", new=AsyncMock(return_value=[{"source": "travel_blog"}])), \
             patch("scrapers.itinerary_corpus.scrape_all_wikivoyage_itineraries", new=AsyncMock(side_effect=Exception("boom"))), \
             patch("scrapers.itinerary_corpus.scrape_reddit_trip_reports", new=AsyncMock(return_value=[{"source": "reddit_trip_report"}])), \
             patch("scrapers.itinerary_corpus.scrape_all_youtube_transcripts", new=AsyncMock(return_value=[])):
            docs = await collect_itinerary_corpus_raw()

        sources = {d["source"] for d in docs}
        assert sources == {"travel_blog", "reddit_trip_report"}
