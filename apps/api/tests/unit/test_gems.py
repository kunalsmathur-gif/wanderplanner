"""
Unit tests for services/gems.py (hidden-gem scoring + crowd dial,
docs/GTM_STRATEGY.md §2). Qdrant scrolls are mocked — fully offline.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import services.gems as gems
from services.gems import (
    compute_gem_intel_sync,
    gem_prompt_block,
    get_gem_intel,
    _sentiment_around,
)


def _poi(name: str, poi_type: str = "attraction") -> dict:
    return {"destination": "Phuket", "name": name, "poi_type": poi_type, "lat": 7.9, "lon": 98.3}


def _chunk(text: str, subreddit: str = "ThailandTourism") -> dict:
    return {"destination": "Phuket", "text": text, "subreddit": subreddit}


def _yt_chunk(text: str) -> dict:
    return {"destination": "Phuket", "text": text, "video_id": "abc123"}


def _mock_client(pois: list[dict], chunks: list[dict], yt_chunks: list[dict] | None = None) -> MagicMock:
    client = MagicMock()
    yt_chunks = yt_chunks or []

    def _scroll(collection_name, scroll_filter, limit, with_payload, with_vectors):
        if collection_name == "osm_pois":
            payloads = pois
        elif collection_name == "reddit":
            payloads = chunks
        elif collection_name == "youtube_comments":
            payloads = yt_chunks
        else:
            payloads = []
        points = []
        for p in payloads:
            pt = MagicMock()
            pt.payload = p
            points.append(pt)
        return points, None

    client.scroll.side_effect = _scroll
    return client


class TestSentimentAround:
    def test_positive_and_negative_counted_in_window(self):
        text = "banana beach is a stunning quiet gem, but patong is crowded and overrated"
        pos, neg = _sentiment_around(text, "banana beach")
        assert pos >= 3  # stunning, quiet, gem
        # patong's negativity is beyond banana beach's ±120 window? window is
        # 120 chars — the whole string fits, so negatives are counted too.
        assert neg >= 1

    def test_no_mention_returns_zero(self):
        assert _sentiment_around("nothing here", "banana beach") == (0, 0)

    def test_hinglish_words_counted(self):
        pos, neg = _sentiment_around("varanasi ghats are ekdum badhiya and sundar", "varanasi ghats")
        assert pos >= 2  # badhiya, sundar
        pos, neg = _sentiment_around("this place is bekar and ganda, total bakwas", "this place")
        assert neg >= 3  # bekar, ganda, bakwas


class TestComputeGemIntel:
    def _run(self, pois, chunks):
        with patch("services.gems.get_qdrant", return_value=_mock_client(pois, chunks)):
            return compute_gem_intel_sync("Phuket")

    def test_low_mention_high_sentiment_is_gem(self):
        pois = [_poi("Banana Beach")]
        chunks = [
            _chunk("Banana Beach is a stunning quiet gem, absolutely loved it"),
            _chunk("if you want peaceful, Banana Beach is underrated and beautiful"),
        ]
        intel = self._run(pois, chunks)
        assert len(intel["gems"]) == 1
        gem = intel["gems"][0]
        assert gem["name"] == "Banana Beach"
        assert gem["mentions"] == 2
        assert gem["sentiment"] > 0.55
        assert "r/ThailandTourism" in gem["sources"]

    def test_high_mention_is_crowd_favourite_not_gem(self):
        pois = [_poi("Patong Beach")]
        chunks = [_chunk(f"visited Patong Beach on day {i}") for i in range(15)]
        intel = self._run(pois, chunks)
        assert intel["gems"] == []
        assert len(intel["crowd_favourites"]) == 1
        assert intel["crowd_favourites"][0]["mentions"] == 15

    def test_zero_mentions_excluded_entirely(self):
        """No community proof → never recommend on OSM presence alone."""
        pois = [_poi("Some Unknown Cove")]
        chunks = [_chunk("talked about other places only")]
        intel = self._run(pois, chunks)
        assert intel["gems"] == []
        assert intel["crowd_favourites"] == []

    def test_negative_sentiment_excluded_from_gems(self):
        pois = [_poi("Scam Corner Market")]
        chunks = [_chunk("Scam Corner Market is overpriced, dirty and a total trap — avoid")]
        intel = self._run(pois, chunks)
        assert intel["gems"] == []

    def test_generic_single_word_names_skipped(self):
        pois = [_poi("Beach"), _poi("Park"), _poi("Zoo")]
        chunks = [_chunk("the beach and the park near the zoo are lovely and quiet")]
        intel = self._run(pois, chunks)
        assert intel["gems"] == []

    def test_empty_collections_return_empty(self):
        assert self._run([], []) == {"gems": [], "crowd_favourites": []}
        assert self._run([_poi("Banana Beach")], []) == {"gems": [], "crowd_favourites": []}

    def test_fewer_mentions_rank_higher_at_equal_sentiment(self):
        pois = [_poi("Quiet Cove"), _poi("Known Cove")]
        chunks = (
            [_chunk("Quiet Cove is a stunning quiet gem")]
            + [_chunk(f"Known Cove is a stunning quiet gem, visit {i}") for i in range(4)]
        )
        intel = self._run(pois, chunks)
        names = [g["name"] for g in intel["gems"]]
        assert names.index("Quiet Cove") < names.index("Known Cove")

    def test_youtube_source_blended_with_reddit(self):
        """docs/NEXT_SESSION_TODO.md item 3 — YouTube comments should
        contribute mentions/sentiment alongside Reddit, with "YouTube"
        provenance distinct from a subreddit label."""
        pois = [_poi("Banana Beach")]
        chunks = [_chunk("Banana Beach is a stunning quiet gem")]
        yt_chunks = [_yt_chunk("Banana Beach was so peaceful and gorgeous, loved it")]
        with patch("services.gems.get_qdrant", return_value=_mock_client(pois, chunks, yt_chunks)):
            intel = compute_gem_intel_sync("Phuket")
        assert len(intel["gems"]) == 1
        gem = intel["gems"][0]
        assert gem["mentions"] == 2
        assert "r/ThailandTourism" in gem["sources"]
        assert "YouTube" in gem["sources"]

    def test_youtube_only_source_still_works_without_reddit(self):
        pois = [_poi("Banana Beach")]
        yt_chunks = [_yt_chunk("Banana Beach is underrated and beautiful, a real gem")]
        with patch("services.gems.get_qdrant", return_value=_mock_client(pois, [], yt_chunks)):
            intel = compute_gem_intel_sync("Phuket")
        assert len(intel["gems"]) == 1
        assert intel["gems"][0]["sources"] == ["YouTube"]


class TestGemPromptBlock:
    _INTEL = {
        "gems": [{
            "name": "Banana Beach", "poi_type": "beach", "lat": 7.9, "lon": 98.3,
            "mentions": 3, "sentiment": 0.9, "sources": ["r/ThailandTourism"],
            "gem_score": 0.4,
        }],
        "crowd_favourites": [{
            "name": "Patong Beach", "poi_type": "beach", "lat": 7.9, "lon": 98.3,
            "mentions": 40, "sentiment": 0.5, "sources": [], "gem_score": 0.09,
        }],
    }

    def test_touristy_returns_empty(self):
        assert gem_prompt_block(self._INTEL, "touristy") == ""

    def test_empty_gems_returns_empty(self):
        assert gem_prompt_block({"gems": [], "crowd_favourites": []}, "offbeat") == ""

    def test_balanced_lists_gems_without_crowd_section(self):
        block = gem_prompt_block(self._INTEL, "balanced")
        assert "Banana Beach" in block
        assert "3 traveller post(s)" in block
        assert "r/ThailandTourism" in block
        assert "90% positive" in block
        assert "CROWD-HEAVY" not in block

    def test_offbeat_includes_crowd_heavy_deprioritisation(self):
        block = gem_prompt_block(self._INTEL, "offbeat")
        assert "Banana Beach" in block
        assert "CROWD-HEAVY" in block
        assert "Patong Beach" in block


@pytest.mark.asyncio
class TestGetGemIntelCache:
    async def test_second_call_served_from_cache(self):
        gems._cache.clear()
        pois = [_poi("Banana Beach")]
        chunks = [_chunk("Banana Beach is a stunning quiet gem")]
        with patch("services.gems.get_qdrant", return_value=_mock_client(pois, chunks)) as mock_get:
            first = await get_gem_intel("Phuket")
            second = await get_gem_intel("Phuket")
        assert first == second
        assert mock_get.call_count == 1  # compute ran once; second call was a cache hit

    async def test_expired_cache_recomputes(self):
        gems._cache.clear()
        pois = [_poi("Banana Beach")]
        chunks = [_chunk("Banana Beach is a stunning quiet gem")]
        with patch("services.gems.get_qdrant", return_value=_mock_client(pois, chunks)) as mock_get:
            await get_gem_intel("Phuket")
            # age the entry past TTL
            ts, intel = gems._cache["Phuket"]
            gems._cache["Phuket"] = (ts - gems._CACHE_TTL_SECONDS - 1, intel)
            await get_gem_intel("Phuket")
        assert mock_get.call_count == 2
