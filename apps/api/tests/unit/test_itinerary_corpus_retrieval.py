"""
Unit tests for services/search.py::retrieve_itinerary_examples
(docs/rag-strategy.md §9 — itinerary_corpus few-shot retrieval).

All embeddings and Qdrant searches are mocked — fully offline.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from models.trip import TripConfig, DestinationInput, GroupComposition, KidAge
from services.search import (
    retrieve_itinerary_examples,
    _corpus_config_query,
    _corpus_duration_days,
    _corpus_group_type,
    _format_corpus_days_brief,
)


def _trip(city: str = "Kyoto", country: str = "Japan", **overrides) -> TripConfig:
    base = dict(
        purpose="cultural",
        pace="moderate",
        destination=DestinationInput(city=city, country=country),
        dates={"start": "2026-11-01", "end": "2026-11-05", "flexible": False},
        group=GroupComposition(adults=2),
    )
    base.update(overrides)
    return TripConfig(**base)


def _hit(point_id: int, score: float, destination: str = "Kyoto", quality: float = 0.9,
         days: list | None = None, source_name: str = "Nomadic Matt") -> MagicMock:
    hit = MagicMock()
    hit.id = point_id
    hit.score = score
    hit.payload = {
        "destination": destination,
        "duration_days": 5,
        "pace": "moderate",
        "purpose": "cultural",
        "group_type": "couple",
        "source_name": source_name,
        "quality_score": quality,
        "days_json": json.dumps(days if days is not None else [
            {"day_number": 1, "theme": "Temples", "places": ["Fushimi Inari", "Gion"], "tips": "Go early"},
        ]),
    }
    return hit


class TestHelpers:
    def test_group_type_mapping(self):
        assert _corpus_group_type(GroupComposition(adults=1)) == "solo"
        assert _corpus_group_type(GroupComposition(adults=2)) == "couple"
        assert _corpus_group_type(GroupComposition(adults=1, seniors=1)) == "couple"
        assert _corpus_group_type(GroupComposition(adults=4)) == "group"
        assert _corpus_group_type(GroupComposition(adults=2, kids=[KidAge(age=6)])) == "family"
        assert _corpus_group_type(GroupComposition(adults=2, infants=1)) == "family"

    def test_duration_from_start_end_inclusive(self):
        assert _corpus_duration_days({"start": "2026-11-01", "end": "2026-11-05"}) == 5

    def test_duration_missing_or_invalid(self):
        assert _corpus_duration_days(None) is None
        assert _corpus_duration_days({"start": None, "end": None}) is None
        assert _corpus_duration_days({"start": "not-a-date", "end": "2026-11-05"}) is None
        # end before start → nonsensical, treated as unknown
        assert _corpus_duration_days({"start": "2026-11-05", "end": "2026-11-01"}) is None

    def test_config_query_mirrors_ingest_config_text(self):
        q = _corpus_config_query(_trip())
        assert q == "5 day moderate cultural couple trip Kyoto Japan"

    def test_format_days_brief(self):
        text = _format_corpus_days_brief([
            {"day_number": 1, "theme": "Temples", "places": ["A", "B"], "tips": "Go early"},
            {"day_number": 2, "theme": "Food", "places": ["C"], "tips": ""},
        ])
        assert "Day 1: Temples. Places: A, B. Tip: Go early" in text
        assert "Day 2: Food. Places: C." in text
        assert "Day 2" in text and "Tip:" not in text.split("\n")[1]


@pytest.mark.asyncio
class TestRetrieveItineraryExamples:
    async def _run(self, trip, config_hits, content_hits, unfiltered=None):
        """Drive retrieve_itinerary_examples with a mocked qdrant client.

        `unfiltered` optionally provides the (config, content) hits returned
        when query_filter is None (the case-insensitive fallback path).
        """
        client = MagicMock()

        def _search(collection_name, query_vector, query_filter, limit, with_payload):
            name = query_vector[0]
            if query_filter is None:
                pair = unfiltered or ([], [])
                return pair[0] if name == "config" else pair[1]
            return config_hits if name == "config" else content_hits

        client.search.side_effect = _search
        with patch("services.search.get_qdrant", return_value=client), \
             patch("services.search.embed", return_value=[[0.1] * 384]):
            return await retrieve_itinerary_examples(trip)

    async def test_returns_formatted_examples(self):
        out = await self._run(_trip(), [_hit(1, 0.9)], [_hit(1, 0.8)])
        assert "[Source: Nomadic Matt" in out
        assert "Day 1: Temples. Places: Fushimi Inari, Gion." in out
        assert "5 days, moderate, cultural, couple" in out

    async def test_weighted_merge_prefers_config_similarity(self):
        # Both docs appear in both result lists, with mirrored scores:
        # doc 1 is the strong CONFIG match, doc 2 the strong CONTENT match.
        # 60/40 weighting must rank the config-similar doc first:
        # doc1 = 0.6*0.9 + 0.4*0.2 = 0.62 > doc2 = 0.6*0.2 + 0.4*0.9 = 0.48.
        out = await self._run(
            _trip(),
            [_hit(1, 0.9, source_name="ConfigMatch"), _hit(2, 0.2, source_name="ContentMatch")],
            [_hit(1, 0.2, source_name="ConfigMatch"), _hit(2, 0.9, source_name="ContentMatch")],
        )
        assert out.index("ConfigMatch") < out.index("ContentMatch")

    async def test_quality_score_reranks_equal_similarity(self):
        # Equal similarity in both vectors (base 0.9 each); only the source-
        # authority quality differs. Both stay above the score floor
        # (0.9*0.6 = 0.54 and 0.9*0.975 = 0.8775), so ordering is purely
        # the quality weighting.
        out = await self._run(
            _trip(),
            [_hit(1, 0.9, quality=0.2, source_name="LowSignal"),
             _hit(2, 0.9, quality=0.95, source_name="Authoritative")],
            [_hit(1, 0.9, quality=0.2, source_name="LowSignal"),
             _hit(2, 0.9, quality=0.95, source_name="Authoritative")],
        )
        assert out.index("Authoritative") < out.index("LowSignal")

    async def test_below_score_floor_returns_empty(self):
        out = await self._run(_trip(), [_hit(1, 0.1)], [_hit(1, 0.1)])
        assert out == ""

    async def test_no_destination_returns_empty(self):
        trip = _trip()
        trip.destination = None
        out = await self._run(trip, [_hit(1, 0.9)], [_hit(1, 0.9)])
        assert out == ""

    async def test_disabled_flag_returns_empty(self):
        with patch("services.search.settings") as mock_settings:
            mock_settings.itinerary_corpus_retrieval_enabled = False
            out = await retrieve_itinerary_examples(_trip())
        assert out == ""

    async def test_unfiltered_fallback_rejects_other_cities(self):
        # Exact-match filter finds nothing; unfiltered fallback returns a
        # case-variant Kyoto doc (kept) and a Bali doc (rejected).
        out = await self._run(
            _trip(),
            [], [],
            unfiltered=(
                [_hit(1, 0.9, destination="kyoto", source_name="CaseVariant"),
                 _hit(2, 0.95, destination="Bali", source_name="WrongCity")],
                [],
            ),
        )
        assert "CaseVariant" in out
        assert "WrongCity" not in out

    async def test_empty_days_json_skipped(self):
        out = await self._run(_trip(), [_hit(1, 0.9, days=[])], [])
        assert out == ""
