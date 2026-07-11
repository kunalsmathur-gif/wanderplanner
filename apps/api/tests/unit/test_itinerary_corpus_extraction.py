"""
Unit tests for chains/itinerary_corpus_extraction_chain.py (docs/rag-strategy.md §9).

All Gemini calls, embeddings, and Qdrant writes are mocked — fully offline.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chains.itinerary_corpus_extraction_chain import (
    ItineraryCorpusDay,
    ItineraryCorpusDoc,
    extract_itinerary_doc,
    compute_quality_score,
    _config_text,
    _content_text,
    ingest_itinerary_corpus,
)


def _make_gemini_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.text = json.dumps(payload)
    return resp


class TestExtractItineraryDoc:
    @pytest.mark.asyncio
    async def test_extracts_valid_itinerary(self):
        payload = {
            "is_itinerary": True,
            "destination": "Kyoto",
            "country": "Japan",
            "duration_days": 5,
            "pace": "moderate",
            "purpose": "cultural",
            "budget_tier": "mid-range",
            "group_type": "couple",
            "published_month": "November",
            "days": [
                {"day_number": 1, "theme": "Old town", "places": ["Fushimi Inari", "Gion"], "tips": "Go early"},
            ],
        }
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_gemini_response(payload)

        with patch("google.genai.Client", return_value=mock_client), \
             patch("chains.itinerary_corpus_extraction_chain.track_gemini_usage"):
            doc = await extract_itinerary_doc("Day 1 in Kyoto: visited Fushimi Inari...")

        assert doc is not None
        assert doc.destination == "Kyoto"
        assert doc.duration_days == 5
        assert len(doc.days) == 1
        assert doc.days[0].places == ["Fushimi Inari", "Gion"]

    @pytest.mark.asyncio
    async def test_non_itinerary_content_returns_none(self):
        payload = {"is_itinerary": False, "days": []}
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_gemini_response(payload)

        with patch("google.genai.Client", return_value=mock_client), \
             patch("chains.itinerary_corpus_extraction_chain.track_gemini_usage"):
            doc = await extract_itinerary_doc("10 Best Cafes in Paris, ranked by ambiance...")

        assert doc is None

    @pytest.mark.asyncio
    async def test_is_itinerary_true_but_no_days_returns_none(self):
        """Even if the LLM says is_itinerary=true, an empty days list means
        nothing usable was actually extracted — treat as a non-match."""
        payload = {"is_itinerary": True, "destination": "Bali", "days": []}
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_gemini_response(payload)

        with patch("google.genai.Client", return_value=mock_client), \
             patch("chains.itinerary_corpus_extraction_chain.track_gemini_usage"):
            doc = await extract_itinerary_doc("Some vague text about Bali")

        assert doc is None

    @pytest.mark.asyncio
    async def test_malformed_json_retries_then_gives_up(self):
        mock_client = MagicMock()
        bad_resp = MagicMock()
        bad_resp.text = "not valid json {{"
        mock_client.models.generate_content.return_value = bad_resp

        with patch("google.genai.Client", return_value=mock_client), \
             patch("chains.itinerary_corpus_extraction_chain.track_gemini_usage"), \
             patch("asyncio.sleep", new=AsyncMock()):
            doc = await extract_itinerary_doc("garbage input")

        assert doc is None
        assert mock_client.models.generate_content.call_count == 3

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self):
        payload = {
            "is_itinerary": True,
            "destination": "Rome",
            "days": [{"day_number": 1, "theme": "Colosseum", "places": ["Colosseum"], "tips": ""}],
        }
        mock_client = MagicMock()
        fenced_resp = MagicMock()
        fenced_resp.text = f"```json\n{json.dumps(payload)}\n```"
        mock_client.models.generate_content.return_value = fenced_resp

        with patch("google.genai.Client", return_value=mock_client), \
             patch("chains.itinerary_corpus_extraction_chain.track_gemini_usage"):
            doc = await extract_itinerary_doc("Day 1: Colosseum...")

        assert doc is not None
        assert doc.destination == "Rome"


class TestComputeQualityScore:
    def test_authoritative_source_scores_high(self):
        assert compute_quality_score({"source": "travel_blog"}) == 0.90
        assert compute_quality_score({"source": "wikivoyage_itinerary"}) == 0.90

    def test_high_karma_reddit_scores_high(self):
        assert compute_quality_score({"source": "reddit_trip_report", "reddit_score": 600}) == 0.85

    def test_standard_reddit_scores_medium(self):
        assert compute_quality_score({"source": "reddit_trip_report", "reddit_score": 100}) == 0.65

    def test_low_signal_reddit_scores_low(self):
        assert compute_quality_score({"source": "reddit_trip_report", "reddit_score": 5}) == 0.40

    def test_youtube_scores_medium_low(self):
        assert compute_quality_score({"source": "youtube_captions"}) == 0.55

    def test_unknown_source_defaults_conservatively(self):
        assert compute_quality_score({"source": "mystery_source"}) == 0.50


class TestConfigAndContentText:
    def test_config_text_includes_all_fields(self):
        doc = ItineraryCorpusDoc(
            destination="Kyoto", country="Japan", duration_days=5,
            pace="moderate", purpose="cultural", group_type="couple",
            published_month="November",
        )
        text = _config_text(doc)
        assert "5 day" in text
        assert "moderate" in text
        assert "cultural" in text
        assert "couple" in text
        assert "Kyoto" in text
        assert "Japan" in text
        assert "November" in text

    def test_config_text_handles_missing_fields_gracefully(self):
        doc = ItineraryCorpusDoc(destination="Goa")
        text = _config_text(doc)
        assert "Goa" in text
        assert "  " not in text  # no double-spaces from empty fields

    def test_content_text_formats_days(self):
        doc = ItineraryCorpusDoc(days=[
            ItineraryCorpusDay(day_number=1, theme="Old town", places=["A", "B"], tips="Go early"),
            ItineraryCorpusDay(day_number=2, theme="Beach day", places=["C"], tips=""),
        ])
        text = _content_text(doc)
        assert "Day 1: Old town" in text
        assert "A, B" in text
        assert "Tip: Go early" in text
        assert "Day 2: Beach day" in text
        assert "Tip:" not in text.split("\n")[1]  # no tip line appended for empty tips


class TestIngestItineraryCorpus:
    @pytest.mark.asyncio
    async def test_full_pipeline_with_mocked_dependencies(self):
        raw_docs = [
            {"source": "travel_blog", "source_name": "Nomadic Matt", "source_url": "https://example.com/1", "raw_text": "Day 1..."},
            {"source": "reddit_trip_report", "source_name": "r/travel", "source_url": "https://example.com/2", "raw_text": "Day 1...", "reddit_score": 600},
        ]
        struct_doc = ItineraryCorpusDoc(
            destination="Bali", country="Indonesia", duration_days=5,
            days=[ItineraryCorpusDay(day_number=1, theme="Beach", places=["Kuta"], tips="")],
        )

        mock_qdrant_client = MagicMock()

        with patch("scrapers.itinerary_corpus.collect_itinerary_corpus_raw", new=AsyncMock(return_value=raw_docs)), \
             patch("chains.itinerary_corpus_extraction_chain.extract_itinerary_doc", new=AsyncMock(return_value=struct_doc)), \
             patch("core.embeddings.embed", return_value=[[0.1] * 384, [0.1] * 384]), \
             patch("core.qdrant.get_qdrant", return_value=mock_qdrant_client):
            count = await ingest_itinerary_corpus()

        assert count == 2
        mock_qdrant_client.upsert.assert_called_once()
        call_kwargs = mock_qdrant_client.upsert.call_args.kwargs
        assert call_kwargs["collection_name"] == "itinerary_corpus"
        assert len(call_kwargs["points"]) == 2

    @pytest.mark.asyncio
    async def test_no_raw_docs_returns_zero(self):
        with patch("scrapers.itinerary_corpus.collect_itinerary_corpus_raw", new=AsyncMock(return_value=[])):
            count = await ingest_itinerary_corpus()
        assert count == 0

    @pytest.mark.asyncio
    async def test_all_extraction_failures_returns_zero(self):
        raw_docs = [{"source": "travel_blog", "source_name": "X", "source_url": "https://x.com", "raw_text": "text"}]
        with patch("scrapers.itinerary_corpus.collect_itinerary_corpus_raw", new=AsyncMock(return_value=raw_docs)), \
             patch("chains.itinerary_corpus_extraction_chain.extract_itinerary_doc", new=AsyncMock(return_value=None)):
            count = await ingest_itinerary_corpus()
        assert count == 0
