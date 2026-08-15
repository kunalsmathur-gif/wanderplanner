"""
Unit tests for services/query_router.py — agentic router classifier
(issue #35, docs/rag-strategy.md §12; eval cases RAG-080/RAG-081).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services.query_router import route_query


class TestRouteQuery:
    @pytest.mark.parametrize("query", [
        "best restaurants in Rome",
        "top temples in Kyoto",
        "best time to visit Kyoto",
        "what should I pack for a trip to Iceland",
        "is Bali safe for solo female travellers",
        "recommend a 5-day itinerary for Vietnam",
    ])
    def test_static_queries_route_to_qdrant(self, query):
        route = route_query(query)
        assert route.source == "qdrant"
        assert route.note is None
        assert route.matched_keywords == ()

    @pytest.mark.parametrize("query", [
        "is it raining in Kyoto right now",
        "any strikes in Paris this week",
        "flight prices to Tokyo this week",
        "what's the weather like in Bali currently",
        "is there a protest in Bangkok today",
        "current price for a Eurostar ticket",
        "is the Louvre open right now",
    ])
    def test_time_sensitive_queries_route_to_web(self, query):
        route = route_query(query)
        assert route.source == "web"
        assert route.note is not None
        assert route.matched_keywords

    def test_rag_080_static_restaurant_query(self):
        # Companion eval case RAG-080.
        route = route_query("best restaurants in Rome")
        assert route.source == "qdrant"

    def test_rag_081_dynamic_flight_price_query(self):
        # Companion eval case RAG-081.
        route = route_query("flight prices to Tokyo this week")
        assert route.source == "web"

    def test_empty_or_none_text_routes_to_qdrant(self):
        assert route_query(None).source == "qdrant"
        assert route_query("").source == "qdrant"

    def test_word_boundary_avoids_false_positive_substrings(self):
        # "today" as a bare substring must not match inside an unrelated word.
        route = route_query("Todayama is a scenic village in Gifu")
        assert route.source == "qdrant"

    def test_matched_keywords_reflect_the_trigger(self):
        route = route_query("is it raining in Kyoto right now")
        assert "right now" in route.matched_keywords
        assert "raining" in route.matched_keywords


class TestWizardChainRouterHint:
    def test_router_hint_returns_note_for_time_sensitive_text(self):
        from chains.wizard_chat_chain import _router_hint_for
        hint = _router_hint_for("is it raining in Kyoto right now")
        assert hint

    def test_router_hint_empty_for_static_text(self):
        from chains.wizard_chat_chain import _router_hint_for
        assert _router_hint_for("I'd like a relaxed 5-day trip to Kyoto") == ""

    def test_router_hint_disabled_by_flag(self):
        from chains.wizard_chat_chain import _router_hint_for
        with patch("chains.wizard_chat_chain.settings") as mock_settings:
            mock_settings.agentic_router_enabled = False
            assert _router_hint_for("is it raining in Kyoto right now") == ""
