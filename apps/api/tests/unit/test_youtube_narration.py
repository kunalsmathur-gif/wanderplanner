"""Unit tests for scrapers/youtube_narration.py (docs/NEXT_SESSION_TODO.md §C).

Fully offline — httpx, Qdrant and youtube_transcript_api are all mocked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scrapers.youtube_narration import (
    _CHUNK_CHARS,
    _narration_chunks,
    destinations_missing_transcripts,
    fetch_video_descriptions,
    ingest_youtube_narration,
    known_video_ids_sync,
)


class TestNarrationChunks:
    def test_splits_punctuated_prose_at_sentence_boundaries(self):
        text = ("We ate at a lovely bistro. " * 40).strip()
        chunks = _narration_chunks(text)

        assert len(chunks) > 1
        assert all(len(c) <= _CHUNK_CHARS + 50 for c in chunks)

    def test_unpunctuated_captions_still_split(self):
        """The whole reason this module doesn't reuse wikivoyage's chunker.

        YouTube auto-captions contain no sentence punctuation at all, so a
        sentence-boundary splitter returns the entire transcript as one chunk.
        """
        caption_text = " ".join(["okay so then we walked over to the market"] * 200)
        assert "." not in caption_text

        chunks = _narration_chunks(caption_text)

        assert len(chunks) > 5, "unpunctuated text must still be chunked"
        assert all(len(c) <= _CHUNK_CHARS + 50 for c in chunks)

    def test_overlap_keeps_an_amount_with_its_context(self):
        """An amount landing near a chunk boundary must not be orphaned from
        the words that say what it bought — core/price_extraction.py scopes
        context to the amount's own sentence, widening only ~90 chars."""
        filler = "we kept walking around the old town for ages " * 12
        text = f"{filler} the thali cost 150 rupees which was great value {filler}"

        chunks = _narration_chunks(text)
        with_amount = [c for c in chunks if "150 rupees" in c]

        assert with_amount, "the amount survived chunking"
        assert any("thali" in c for c in with_amount), "amount kept its context word"

    def test_drops_trivially_short_fragments(self):
        assert _narration_chunks("too short") == []


class TestKnownVideoIds:
    def test_reads_distinct_videos_from_comments_collection(self):
        """Discovery must cost zero API calls — it reads back what the comment
        backfill already stored."""
        def _point(video_id, title):
            p = MagicMock()
            p.payload = {"video_id": video_id, "video_title": title}
            return p

        fake_client = MagicMock()
        fake_client.scroll.return_value = (
            [_point("a", "Jaipur Vlog"), _point("a", "Jaipur Vlog"), _point("b", "Jaipur Food")],
            None,
        )

        with patch("scrapers.youtube_narration.get_qdrant", return_value=fake_client):
            videos = known_video_ids_sync("Jaipur")

        assert sorted(v["video_id"] for v in videos) == ["a", "b"]
        assert {v["title"] for v in videos} == {"Jaipur Vlog", "Jaipur Food"}


class TestFetchVideoDescriptions:
    @pytest.mark.asyncio
    async def test_no_key_is_a_noop(self):
        with patch("scrapers.youtube_narration.settings.youtube_api_key", ""):
            assert await fetch_video_descriptions(["a"]) == {}

    @pytest.mark.asyncio
    async def test_batches_fifty_ids_per_call(self):
        """videos.list costs 1 unit per call and accepts 50 ids — batching is
        what keeps this source ~20 units for a full run."""
        calls: list[dict] = []

        async def _get(url, params=None):
            calls.append(params)
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={"items": []})
            return resp

        client = MagicMock()
        client.get = _get
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.youtube_narration.settings.youtube_api_key", "k"), \
             patch("scrapers.youtube_narration.httpx.AsyncClient", return_value=client):
            await fetch_video_descriptions([f"v{i}" for i in range(120)])

        assert len(calls) == 3
        assert len(calls[0]["id"].split(",")) == 50
        assert len(calls[2]["id"].split(",")) == 20

    @pytest.mark.asyncio
    async def test_quota_refusal_is_terminal_not_retried(self):
        """Matches the v10.40.3 rule: a 403/429 is terminal for the day."""
        attempts = 0

        async def _get(url, params=None):
            nonlocal attempts
            attempts += 1
            resp = MagicMock()
            resp.status_code = 403
            return resp

        client = MagicMock()
        client.get = _get
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.youtube_narration.settings.youtube_api_key", "k"), \
             patch("scrapers.youtube_narration.httpx.AsyncClient", return_value=client):
            out = await fetch_video_descriptions(["a", "b"])

        assert out == {}
        assert attempts == 1, "must not retry a quota refusal"


class TestIngestYoutubeNarration:
    @pytest.mark.asyncio
    async def test_no_known_videos_is_a_clean_zero(self):
        with patch("scrapers.youtube_narration.known_video_ids_sync", return_value=[]):
            assert await ingest_youtube_narration("Nowhere") == 0

    @pytest.mark.asyncio
    async def test_stores_transcript_and_description_with_distinct_sources(self):
        long_text = "The thali here cost 150 rupees and the room was 2000 a night. " * 12
        fake_client = MagicMock()

        with patch("scrapers.youtube_narration.known_video_ids_sync",
                   return_value=[{"video_id": "v1", "title": "Jaipur on a budget"}]), \
             patch("scrapers.youtube_narration.fetch_video_descriptions",
                   new=AsyncMock(return_value={"v1": long_text})), \
             patch("scrapers.youtube_narration._transcript_text",
                   new=AsyncMock(return_value=long_text)), \
             patch("scrapers.youtube_narration.embed", side_effect=lambda t: [[0.0] * 384] * len(t)), \
             patch("scrapers.youtube_narration.get_qdrant", return_value=fake_client), \
             patch("scrapers.youtube_narration.delete_stale_destination_points", return_value=0):
            stored = await ingest_youtube_narration("Jaipur")

        assert stored > 0
        points = fake_client.upsert.call_args.kwargs["points"]
        sources = {p.payload["source"] for p in points}
        assert sources == {"youtube_description", "youtube_transcript"}
        assert all(p.payload["destination"] == "Jaipur" for p in points)

    @pytest.mark.asyncio
    async def test_missing_captions_still_ingests_the_description(self):
        """Most videos have no English captions; a description alone is still
        worth storing (it's where explicit cost breakdowns live)."""
        long_text = "Full cost breakdown: hotel 2000 per night, food 600 per day. " * 12
        fake_client = MagicMock()

        with patch("scrapers.youtube_narration.known_video_ids_sync",
                   return_value=[{"video_id": "v1", "title": "T"}]), \
             patch("scrapers.youtube_narration.fetch_video_descriptions",
                   new=AsyncMock(return_value={"v1": long_text})), \
             patch("scrapers.youtube_narration._transcript_text", new=AsyncMock(return_value="")), \
             patch("scrapers.youtube_narration.embed", side_effect=lambda t: [[0.0] * 384] * len(t)), \
             patch("scrapers.youtube_narration.get_qdrant", return_value=fake_client), \
             patch("scrapers.youtube_narration.delete_stale_destination_points", return_value=0):
            stored = await ingest_youtube_narration("Jaipur")

        assert stored > 0
        points = fake_client.upsert.call_args.kwargs["points"]
        assert {p.payload["source"] for p in points} == {"youtube_description"}


class TestHindiNarrationContext:
    """Indian destination vlogs are largely Hindi-only; the price path has to
    survive that or the India-first corpus contributes nothing."""

    def test_hindi_food_and_stay_context_is_recognised(self):
        from core.keyword_match import has_keyword
        from core.price_extraction import FOOD_CONTEXT_KEYWORDS, STAY_CONTEXT_KEYWORDS

        assert has_keyword("यहां थाली ₹150 की मिलती है", FOOD_CONTEXT_KEYWORDS)
        assert has_keyword("होटल का रूम ₹2000 पर नाइट", STAY_CONTEXT_KEYWORDS)

    def test_hindi_transport_counts_as_competing_spend_not_food(self):
        """Without Hindi in OTHER_SPEND_KEYWORDS, the two most commonly priced
        items in an Indian vlog — rickshaw fares and entry tickets — could be
        read as meal prices by an amount borrowing context across a sentence."""
        from core.keyword_match import has_keyword
        from core.price_extraction import FOOD_CONTEXT_KEYWORDS, OTHER_SPEND_KEYWORDS

        fare = "ऑटो रिक्शा का कॉस्ट ₹1000 पर डे"
        assert has_keyword(fare, OTHER_SPEND_KEYWORDS)
        assert not has_keyword(fare, FOOD_CONTEXT_KEYWORDS)

    def test_transcript_languages_prefer_english_then_hindi(self):
        from scrapers.youtube_narration import _TRANSCRIPT_LANGUAGES

        assert _TRANSCRIPT_LANGUAGES[0] == "en", "English still preferred where it exists"
        assert "hi" in _TRANSCRIPT_LANGUAGES


class TestPriceCollectionWiring:
    def test_narration_is_in_the_price_path_but_not_the_gems_path(self):
        """The whole point of a separate collection: narration must reach cost
        grounding, and must NOT reach gems.py's mention counting, where one
        vlogger repeating a name would read as many independent endorsements.
        """
        import inspect

        from core.config import settings
        from core.cost_grounding import _price_collections

        assert settings.qdrant_collection_youtube_narration in _price_collections()

        import services.gems as gems
        assert "youtube_narration" not in inspect.getsource(gems)


class TestDestinationsMissingTranscripts:
    """Feeds the scheduler's slow drip-retry job (core/scheduler.py::
    _retry_youtube_narration_transcripts, issue #46 follow-up) — must find
    exactly the destinations whose narration points are description-only."""

    def _point(self, destination, source):
        p = MagicMock()
        p.payload = {"destination": destination, "source": source}
        return p

    @pytest.mark.asyncio
    async def test_finds_description_only_destinations(self):
        points = [
            self._point("Jaipur", "youtube_description"),
            self._point("Jaipur", "youtube_description"),
            self._point("Paris", "youtube_transcript"),
            self._point("Paris", "youtube_description"),
        ]
        fake_client = MagicMock()
        fake_client.scroll.return_value = (points, None)

        with patch("scrapers.youtube_narration.get_qdrant", return_value=fake_client):
            missing = await destinations_missing_transcripts()

        assert missing == ["Jaipur"]

    @pytest.mark.asyncio
    async def test_destination_with_any_transcript_chunk_is_not_missing(self):
        points = [
            self._point("Tokyo", "youtube_transcript"),
            self._point("Tokyo", "youtube_description"),
        ]
        fake_client = MagicMock()
        fake_client.scroll.return_value = (points, None)

        with patch("scrapers.youtube_narration.get_qdrant", return_value=fake_client):
            missing = await destinations_missing_transcripts()

        assert missing == []

    @pytest.mark.asyncio
    async def test_no_narration_at_all_returns_empty(self):
        fake_client = MagicMock()
        fake_client.scroll.return_value = ([], None)

        with patch("scrapers.youtube_narration.get_qdrant", return_value=fake_client):
            missing = await destinations_missing_transcripts()

        assert missing == []

    @pytest.mark.asyncio
    async def test_paginates_across_multiple_scroll_pages(self):
        page1 = ([self._point("A", "youtube_description")], "cursor-1")
        page2 = ([self._point("B", "youtube_transcript")], None)
        fake_client = MagicMock()
        fake_client.scroll.side_effect = [page1, page2]

        with patch("scrapers.youtube_narration.get_qdrant", return_value=fake_client):
            missing = await destinations_missing_transcripts()

        assert missing == ["A"]
