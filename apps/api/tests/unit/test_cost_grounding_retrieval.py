"""Tests for the lexical half of core/cost_grounding.py's price retrieval.

Background: stay/food grounding was a live no-op even after the extraction
regex was widened to catch bare numbers, because *retrieval* never surfaced
the snippets containing them. Dense vector search ranks by similarity to a
price-flavoured query, but a casual "Choki dani 700 per person" comment is
topically about a restaurant, not about "cost", so it never made the top-N
cut. Presence of a price is a lexical property, so it's now tested lexically
(`_scroll_price_candidates_sync`) alongside the semantic pass.

Qdrant is mocked throughout — fully offline.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.cost_grounding import (
    _scroll_price_candidates_sync,
    community_price_samples,
)
from core.price_extraction import FOOD_CONTEXT_KEYWORDS


def _mock_client(texts_by_collection: dict[str, list[str]]) -> MagicMock:
    client = MagicMock()

    def _scroll(collection_name, scroll_filter, limit, with_payload, with_vectors):
        points = []
        for text in texts_by_collection.get(collection_name, []):
            point = MagicMock()
            point.payload = {"destination": "Jaipur", "text": text}
            points.append(point)
        return points, None

    client.scroll.side_effect = _scroll
    return client


class TestLexicalPriceSweep:
    def _run(self, texts_by_collection, context_keywords=None, collections=None):
        client = _mock_client(texts_by_collection)
        with patch("core.qdrant.get_qdrant", return_value=client):
            return _scroll_price_candidates_sync(
                "Jaipur",
                collections or ["wiki", "reddit", "youtube_comments"],
                context_keywords,
            )

    def test_finds_casual_bare_number_price_dense_search_would_miss(self):
        """The exact live case that motivated this: a real price mention with
        almost no topical 'cost' signal for an embedding to rank on."""
        snippets = self._run({"youtube_comments": ["Choki dani 700 per person, totally worth it"]})
        assert len(snippets) == 1
        assert "700 per person" in snippets[0]

    def test_skips_chunks_with_no_price_at_all(self):
        snippets = self._run({"wiki": ["Jaipur is known for its pink sandstone architecture."]})
        assert snippets == []

    def test_applies_context_keyword_filter(self):
        """An in-bounds amount in an off-topic chunk must not be collected —
        same guard the extractor applies (a club cover charge is not a meal)."""
        snippets = self._run(
            {"wiki": ["Nightclub entry is ₹800 at the door."]},
            context_keywords=FOOD_CONTEXT_KEYWORDS,
        )
        assert snippets == []

        on_topic = self._run(
            {"wiki": ["Dinner at the restaurant was ₹800 per person."]},
            context_keywords=FOOD_CONTEXT_KEYWORDS,
        )
        assert len(on_topic) == 1

    def test_sweeps_every_configured_collection(self):
        snippets = self._run({
            "wiki": ["A thali costs ₹250 at most places."],
            "reddit": ["We paid ₹1200 per night there."],
            "youtube_comments": ["ticket 500 per person"],
        })
        assert len(snippets) == 3

    def test_returns_full_chunk_so_every_price_in_it_stays_extractable(self):
        """This path feeds a regex, not a prompt, so it must not truncate: a
        280-char excerpt centred on the first price would silently drop the
        others, and the median needs all of them (Wikivoyage 'Eat' sections
        routinely list several prices in one chunk)."""
        text = (
            "Eat: the thali was ₹250 per plate. " + "filler words here " * 30
            + "and the buffet dinner ran ₹700 per person."
        )
        snippets = self._run({"wiki": [text]})
        assert snippets == [text]

        from core.price_extraction import extract_price_mentions_inr
        amounts = extract_price_mentions_inr(
            snippets, 100, 10_000, context_keywords=FOOD_CONTEXT_KEYWORDS
        )
        assert amounts == [250.0, 700.0]

    def test_missing_collection_is_skipped_not_fatal(self):
        """A collection that doesn't exist yet (or isn't indexed) must degrade
        to 'no snippets from there', never break cost estimation."""
        client = MagicMock()

        def _scroll(collection_name, **kwargs):
            if collection_name == "reddit":
                raise RuntimeError("collection not found")
            point = MagicMock()
            point.payload = {"text": "Thali ₹250 per plate here."}
            return [point], None

        client.scroll.side_effect = _scroll
        with patch("core.qdrant.get_qdrant", return_value=client):
            snippets = _scroll_price_candidates_sync("Jaipur", ["wiki", "reddit"], None)
        assert len(snippets) == 1

    def test_handles_text_preview_payload_key(self):
        client = MagicMock()
        point = MagicMock()
        point.payload = {"text_preview": "Dinner was ₹400 per person."}
        client.scroll.return_value = ([point], None)
        with patch("core.qdrant.get_qdrant", return_value=client):
            snippets = _scroll_price_candidates_sync("Jaipur", ["wiki"], None)
        assert len(snippets) == 1


class TestCommunityPriceSamples:
    @pytest.mark.asyncio
    async def test_lexical_hits_come_first_and_semantic_complements_them(self):
        with patch(
            "core.cost_grounding._scroll_price_candidates_sync",
            return_value=["lexical ₹250 per plate"],
        ), patch(
            "core.cost_grounding.community_price_snippets",
            new=AsyncMock(return_value=["semantic snippet about costs"]),
        ):
            samples = await community_price_samples("Jaipur", "food meal daily cost per person")
        assert samples == ["lexical ₹250 per plate", "semantic snippet about costs"]

    @pytest.mark.asyncio
    async def test_dedupes_a_chunk_found_by_both_passes(self):
        shared = "Dinner at the dhaba was ₹300 per person, great value"
        with patch(
            "core.cost_grounding._scroll_price_candidates_sync", return_value=[shared]
        ), patch(
            "core.cost_grounding.community_price_snippets", new=AsyncMock(return_value=[shared])
        ):
            samples = await community_price_samples("Jaipur", "food meal daily cost per person")
        assert samples == [shared]

    @pytest.mark.asyncio
    async def test_caps_total_samples(self):
        from core.cost_grounding import _MAX_PRICE_SAMPLES

        many = [f"Thali number {i} was ₹{200 + i} per plate" for i in range(100)]
        with patch(
            "core.cost_grounding._scroll_price_candidates_sync", return_value=many
        ), patch(
            "core.cost_grounding.community_price_snippets", new=AsyncMock(return_value=[])
        ):
            samples = await community_price_samples("Jaipur", "food meal daily cost per person")
        assert len(samples) == _MAX_PRICE_SAMPLES

    @pytest.mark.asyncio
    async def test_lexical_failure_degrades_to_semantic_only(self):
        with patch(
            "core.cost_grounding._scroll_price_candidates_sync",
            side_effect=RuntimeError("qdrant down"),
        ), patch(
            "core.cost_grounding.community_price_snippets",
            new=AsyncMock(return_value=["semantic only"]),
        ):
            samples = await community_price_samples("Jaipur", "food meal daily cost per person")
        assert samples == ["semantic only"]

    @pytest.mark.asyncio
    async def test_empty_destination_returns_nothing(self):
        assert await community_price_samples("", "food") == []
