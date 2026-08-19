"""
Unit tests for services/generated_itineraries.py — the `generated_itineraries`
Qdrant collection "learning flywheel" (issue #32).

All embeddings and Qdrant client calls are mocked — fully offline.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from models.trip import DestinationInput, GroupComposition, TripConfig
from services.generated_itineraries import (
    _content_text_from_raw_days,
    _corpus_days_json,
    compute_generation_id,
    retrieve_generated_itinerary_examples,
    store_generated_itinerary,
)


def _trip(city: str = "Kyoto", country: str = "Japan", **overrides) -> TripConfig:
    base: dict[str, Any] = dict(
        purpose="cultural",
        pace="moderate",
        destination=DestinationInput(city=city, country=country),
        dates={"start": "2026-11-01", "end": "2026-11-05", "flexible": False},
        group=GroupComposition(adults=2),
    )
    base.update(overrides)
    return TripConfig(**base)


def _raw(days: list[dict] | None = None, **overrides) -> dict[str, Any]:
    base: dict[str, Any] = {
        "days": days
        if days is not None
        else [
            {
                "day_number": 1,
                "theme": "Temples",
                "items": [{"title": "Fushimi Inari"}, {"title": "Gion"}],
            },
        ],
    }
    base.update(overrides)
    return base


def _hit(point_id: int, score: float, destination: str = "Kyoto", quality: float = 0.75,
         days: list | None = None) -> MagicMock:
    hit = MagicMock()
    hit.id = point_id
    hit.score = score
    hit.payload = {
        "destination": destination,
        "duration_days": 5,
        "pace": "moderate",
        "purpose": "cultural",
        "group_type": "couple",
        "quality_score": quality,
        "days_json": json.dumps(
            days
            if days is not None
            else [{"day_number": 1, "theme": "Temples", "places": ["Fushimi Inari", "Gion"], "tips": ""}]
        ),
    }
    return hit


class TestHelpers:
    def test_content_text_from_raw_days(self):
        text = _content_text_from_raw_days(_raw()["days"])
        assert "Day 1: Temples. Places: Fushimi Inari, Gion." in text

    def test_corpus_days_json_reshapes_items_to_places(self):
        reshaped = json.loads(_corpus_days_json(_raw()["days"]))
        assert reshaped == [
            {"day_number": 1, "theme": "Temples", "places": ["Fushimi Inari", "Gion"], "tips": ""}
        ]


class TestComputeGenerationId:
    def test_returns_none_when_disabled(self):
        with patch("services.generated_itineraries.settings") as mock_settings:
            mock_settings.generated_itineraries_store_enabled = False
            assert compute_generation_id(_trip(), _raw()) is None

    def test_returns_none_when_no_destination(self):
        trip = _trip()
        trip.destination = None
        assert compute_generation_id(trip, _raw()) is None

    def test_returns_none_when_no_days(self):
        assert compute_generation_id(_trip(), _raw(days=[])) is None

    def test_returns_a_stringified_int_id(self):
        gen_id = compute_generation_id(_trip(), _raw())
        assert gen_id is not None
        assert gen_id.isdigit()


@pytest.mark.asyncio
class TestStoreGeneratedItinerary:
    async def _run(self, trip, raw):
        client = MagicMock()
        with patch("services.generated_itineraries.get_qdrant", return_value=client), \
             patch("services.generated_itineraries.embed", return_value=[[0.1] * 384, [0.2] * 384]):
            await store_generated_itinerary(trip, raw)
        return client

    async def test_upserts_with_dual_named_vectors(self):
        client = await self._run(_trip(), _raw())
        client.upsert.assert_called_once()
        kwargs = client.upsert.call_args.kwargs
        point = kwargs["points"][0]
        assert set(point.vector.keys()) == {"config", "content"}
        assert point.payload["destination"] == "Kyoto"
        assert point.payload["source_name"] == "wanderplanner_generated"

    async def test_quality_score_lower_when_not_context_grounded(self):
        client = await self._run(_trip(), _raw(_context_grounded=False))
        point = client.upsert.call_args.kwargs["points"][0]
        assert point.payload["quality_score"] == 0.55

    async def test_quality_score_default_when_context_grounded(self):
        client = await self._run(_trip(), _raw())
        point = client.upsert.call_args.kwargs["points"][0]
        assert point.payload["quality_score"] == 0.75

    async def test_skips_when_no_destination(self):
        trip = _trip()
        trip.destination = None
        client = await self._run(trip, _raw())
        client.upsert.assert_not_called()

    async def test_skips_when_no_days(self):
        client = await self._run(_trip(), _raw(days=[]))
        client.upsert.assert_not_called()

    async def test_disabled_flag_skips_write(self):
        with patch("services.generated_itineraries.settings") as mock_settings:
            mock_settings.generated_itineraries_store_enabled = False
            client = MagicMock()
            with patch("services.generated_itineraries.get_qdrant", return_value=client):
                await store_generated_itinerary(_trip(), _raw())
            client.upsert.assert_not_called()

    async def test_write_failure_is_swallowed(self):
        client = MagicMock()
        client.upsert.side_effect = RuntimeError("boom")
        with patch("services.generated_itineraries.get_qdrant", return_value=client), \
             patch("services.generated_itineraries.embed", return_value=[[0.1] * 384, [0.2] * 384]):
            # Must not raise.
            await store_generated_itinerary(_trip(), _raw())

    async def test_uses_precomputed_point_id_when_given(self):
        """Issue #34: the id handed back to the client as `generation_id`
        must be the exact same id the Qdrant point is written under, so
        later session-signal reports can find it again."""
        client = MagicMock()
        with patch("services.generated_itineraries.get_qdrant", return_value=client), \
             patch("services.generated_itineraries.embed", return_value=[[0.1] * 384, [0.2] * 384]):
            await store_generated_itinerary(_trip(), _raw(), point_id="123456789")
        point = client.upsert.call_args.kwargs["points"][0]
        assert point.id == 123456789


@pytest.mark.asyncio
class TestRetrieveGeneratedItineraryExamples:
    async def _run(self, trip, config_hits, content_hits, unfiltered=None):
        client = MagicMock()

        def _search(collection_name, query_vector, query_filter, limit, with_payload):
            name = query_vector[0]
            if query_filter is None:
                pair = unfiltered or ([], [])
                return pair[0] if name == "config" else pair[1]
            return config_hits if name == "config" else content_hits

        client.search.side_effect = _search
        with patch("services.generated_itineraries.get_qdrant", return_value=client), \
             patch("services.generated_itineraries.embed", return_value=[[0.1] * 384]):
            return await retrieve_generated_itinerary_examples(trip)

    async def test_returns_formatted_examples(self):
        out = await self._run(_trip(), [_hit(1, 0.9)], [_hit(1, 0.8)])
        assert "previously generated Wanderplanner itinerary" in out
        assert "Day 1: Temples. Places: Fushimi Inari, Gion." in out

    async def test_below_score_floor_returns_empty(self):
        out = await self._run(_trip(), [_hit(1, 0.1)], [_hit(1, 0.1)])
        assert out == ""

    async def test_no_destination_returns_empty(self):
        trip = _trip()
        trip.destination = None
        out = await self._run(trip, [_hit(1, 0.9)], [_hit(1, 0.9)])
        assert out == ""

    async def test_disabled_flag_returns_empty(self):
        with patch("services.generated_itineraries.settings") as mock_settings:
            mock_settings.generated_itineraries_retrieval_enabled = False
            out = await retrieve_generated_itinerary_examples(_trip())
        assert out == ""

    async def test_retrieval_failure_returns_empty_not_raise(self):
        client = MagicMock()
        client.search.side_effect = RuntimeError("boom")
        with patch("services.generated_itineraries.get_qdrant", return_value=client), \
             patch("services.generated_itineraries.embed", return_value=[[0.1] * 384]):
            out = await retrieve_generated_itinerary_examples(_trip())
        assert out == ""
