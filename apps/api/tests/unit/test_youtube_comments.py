"""
Unit tests for scrapers/youtube_comments.py (docs/NEXT_SESSION_TODO.md item 3
— hidden-gems alternative source while Reddit ingestion stays blocked on API
approval). No YOUTUBE_API_KEY is available in this environment yet, so every
test here mocks httpx/Qdrant — fully offline, same pattern as
tests/unit/test_osm_scraper.py and tests/unit/test_wikivoyage_scraper.py.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scrapers.youtube_comments import (
    fetch_video_comments,
    ingest_youtube_comments,
    search_travel_videos,
)

SEARCH_RESPONSE = {
    "items": [
        {"id": {"videoId": "vid1"}, "snippet": {"title": "Best Hidden Places in Jaipur"}},
        {"id": {"videoId": "vid2"}, "snippet": {"title": "Jaipur Travel Guide"}},
        # Missing videoId/title should be skipped, not crash.
        {"id": {}, "snippet": {"title": "No video id"}},
    ]
}

COMMENTS_RESPONSE = {
    "items": [
        {
            "snippet": {
                "topLevelComment": {
                    "id": "c1",
                    "snippet": {"textDisplay": "Amboli Fort was such an underrated gem, loved it!", "likeCount": 12},
                }
            }
        },
        {
            "snippet": {
                "topLevelComment": {
                    "id": "c2",
                    "snippet": {"textDisplay": "nice", "likeCount": 0},  # too short, should be dropped
                }
            }
        },
    ]
}


def _mock_response(json_data: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


class TestSearchTravelVideos:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_empty_without_request(self):
        with patch("scrapers.youtube_comments.settings.youtube_api_key", ""), \
             patch("scrapers.youtube_comments.httpx.AsyncClient") as mock_client_cls:
            videos = await search_travel_videos("Jaipur")

        assert videos == []
        mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_parses_videos_and_skips_malformed_entries(self):
        with patch("scrapers.youtube_comments.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.httpx.AsyncClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(return_value=_mock_response(SEARCH_RESPONSE))
            videos = await search_travel_videos("Jaipur")

        assert len(videos) == 2
        assert videos[0] == {"video_id": "vid1", "title": "Best Hidden Places in Jaipur"}

    @pytest.mark.asyncio
    async def test_retries_transient_failure_then_succeeds(self):
        with patch("scrapers.youtube_comments.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.httpx.AsyncClient") as mock_client_cls, \
             patch("scrapers.youtube_comments.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(side_effect=[Exception("timeout"), _mock_response(SEARCH_RESPONSE)])
            videos = await search_travel_videos("Jaipur")

        assert len(videos) == 2
        assert mock_sleep.await_count == 1

    @pytest.mark.asyncio
    async def test_returns_empty_after_exhausting_retries(self):
        with patch("scrapers.youtube_comments.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.httpx.AsyncClient") as mock_client_cls, \
             patch("scrapers.youtube_comments.asyncio.sleep", new=AsyncMock()):
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(side_effect=Exception("down"))
            videos = await search_travel_videos("Jaipur")

        assert videos == []
        assert mock_client.get.await_count == 3


class TestFetchVideoComments:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_empty_without_request(self):
        with patch("scrapers.youtube_comments.settings.youtube_api_key", ""), \
             patch("scrapers.youtube_comments.httpx.AsyncClient") as mock_client_cls:
            comments = await fetch_video_comments("vid1")

        assert comments == []
        mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_parses_comments_and_drops_too_short(self):
        with patch("scrapers.youtube_comments.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.httpx.AsyncClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(return_value=_mock_response(COMMENTS_RESPONSE))
            comments = await fetch_video_comments("vid1")

        assert len(comments) == 1
        assert "Amboli Fort" in comments[0]["text"]
        assert comments[0]["like_count"] == 12

    @pytest.mark.asyncio
    async def test_403_comments_disabled_returns_empty_without_retry(self):
        """A 403 (comments disabled on this video) is an expected, permanent
        outcome for that video — not a transient failure — so it must not
        burn all 3 retry attempts."""
        with patch("scrapers.youtube_comments.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.httpx.AsyncClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(return_value=_mock_response({}, status_code=403))
            comments = await fetch_video_comments("vid1")

        assert comments == []
        assert mock_client.get.await_count == 1


class TestIngestYoutubeComments:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_zero(self):
        with patch("scrapers.youtube_comments.settings.youtube_api_key", ""):
            count = await ingest_youtube_comments("Jaipur")
        assert count == 0

    @pytest.mark.asyncio
    async def test_no_videos_found_returns_zero(self):
        with patch("scrapers.youtube_comments.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.search_travel_videos", new=AsyncMock(return_value=[])):
            count = await ingest_youtube_comments("Jaipur")
        assert count == 0

    @pytest.mark.asyncio
    async def test_full_flow_embeds_and_upserts_with_orphan_cleanup(self):
        mock_qdrant = MagicMock()
        videos = [{"video_id": "vid1", "title": "Best Hidden Places in Jaipur"}]
        comments = [{"text": "Amboli Fort was such an underrated gem", "comment_id": "c1", "like_count": 12}]

        with patch("scrapers.youtube_comments.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.search_travel_videos", new=AsyncMock(return_value=videos)), \
             patch("scrapers.youtube_comments.fetch_video_comments", new=AsyncMock(return_value=comments)), \
             patch("scrapers.youtube_comments.embed", return_value=[[0.1] * 384]), \
             patch("scrapers.youtube_comments.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.youtube_comments.delete_stale_destination_points", return_value=2) as mock_delete:
            count = await ingest_youtube_comments("Jaipur")

        assert count == 1
        mock_delete.assert_called_once()
        args, _ = mock_delete.call_args
        assert args[0] is mock_qdrant
        assert args[2] == "Jaipur"
        mock_qdrant.upsert.assert_called_once()
        upserted_points = mock_qdrant.upsert.call_args.kwargs["points"]
        assert upserted_points[0].payload["destination"] == "Jaipur"
        assert upserted_points[0].payload["video_id"] == "vid1"

    @pytest.mark.asyncio
    async def test_videos_with_no_comments_returns_zero_without_upsert(self):
        videos = [{"video_id": "vid1", "title": "Best Hidden Places in Jaipur"}]
        mock_qdrant = MagicMock()

        with patch("scrapers.youtube_comments.settings.youtube_api_key", "fake-key"), \
             patch("scrapers.youtube_comments.search_travel_videos", new=AsyncMock(return_value=videos)), \
             patch("scrapers.youtube_comments.fetch_video_comments", new=AsyncMock(return_value=[])), \
             patch("scrapers.youtube_comments.get_qdrant", return_value=mock_qdrant):
            count = await ingest_youtube_comments("Jaipur")

        assert count == 0
        mock_qdrant.upsert.assert_not_called()
