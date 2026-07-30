"""
Unit tests for eval/run_rag_eval.py (issue #50 — wire the golden-dataset
retrieval harness to the real `retrieve_context()` production path).

All Qdrant/embedding/rerank calls are mocked — fully offline. These tests
exist specifically to catch drift back to the old isolated `semantic_search()`
path: if a future edit swaps `evaluate_query()` back to calling
`semantic_search()` directly, `test_evaluate_query_calls_retrieve_context`
fails immediately instead of silently reverting the fix.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from eval.run_rag_eval import build_trip_config, evaluate_query
from models.trip import TripConfig


def test_build_trip_config_plain_case_has_no_persona_purpose_crowd_tags():
    """A case with no persona/purpose/crowd override (e.g. a plain food or
    safety query) should synthesize a bare destination-only TripConfig —
    retrieve_context()'s always-on third query variant already covers those
    topics without needing a tag."""
    q = {"id": "q_paris_food", "destination": "Paris", "query": "vegetarian food options in Paris"}
    config = build_trip_config(q)

    assert isinstance(config, TripConfig)
    assert config.destination is not None
    assert config.destination.city == "Paris"
    assert config.personas == []
    assert config.purpose == ""
    assert config.crowd_preference == "balanced"


def test_build_trip_config_persona_case():
    q = {
        "id": "q_bali_nomad",
        "destination": "Bali",
        "query": "coworking spaces for digital nomads in Bali",
        "personas": ["digital_nomad"],
    }
    config = build_trip_config(q)
    assert config.personas == ["digital_nomad"]


def test_build_trip_config_purpose_case():
    q = {
        "id": "q_paris_family",
        "destination": "Paris",
        "query": "Paris activities for young kids",
        "purpose": "family_vacation",
    }
    config = build_trip_config(q)
    assert config.purpose == "family_vacation"


def test_build_trip_config_crowd_preference_case():
    q = {
        "id": "q_rome_hidden",
        "destination": "Rome",
        "query": "secret viewpoints hidden gems in Rome",
        "crowd_preference": "offbeat",
    }
    config = build_trip_config(q)
    assert config.crowd_preference == "offbeat"


@pytest.mark.asyncio
async def test_evaluate_query_calls_retrieve_context_not_semantic_search():
    """The regression guard: evaluate_query() must call the real
    `retrieve_context()` production path (issue #50), not the isolated
    `semantic_search()` path it used before."""
    q = {
        "id": "q_bali_nomad",
        "destination": "Bali",
        "query": "coworking spaces for digital nomads in Bali",
        "personas": ["digital_nomad"],
        "relevant_ids": ["bali_01"],
    }
    fake_hits = [
        {"text": "chunk one", "source": "wiki", "url": "", "score": 0.9, "published_date": None},
        {"text": "chunk two", "source": "reddit", "url": "", "score": 0.5, "published_date": None},
    ]

    with patch("eval.run_rag_eval.retrieve_context", new=AsyncMock(return_value=fake_hits)) as mock_retrieve:
        result = await evaluate_query(q)

    mock_retrieve.assert_awaited_once()
    called_config, kwargs = mock_retrieve.call_args.args[0], mock_retrieve.call_args.kwargs
    assert isinstance(called_config, TripConfig)
    assert called_config.destination.city == "Bali"
    assert called_config.personas == ["digital_nomad"]
    # Must mirror the real itinerary-generation call site (reranking on).
    assert kwargs.get("enable_reranking") is True

    assert result["retrieved_texts"] == ["chunk one", "chunk two"]
    assert result["relevant"] == {"bali_01"}
