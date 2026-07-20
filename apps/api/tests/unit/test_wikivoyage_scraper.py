"""
Unit tests for scrapers/wikivoyage.py's section-content extraction.

Live-verified 2026-07-20: MediaWiki's current skin wraps each `<h2>` section
heading in a `<div class="mw-heading mw-heading2">` instead of leaving the
heading as a direct sibling of its section content. `scrape_wikivoyage` used
to walk `h2.find_next_siblings()`, which — once headings moved inside a
wrapper div — only ever found the wrapper's own children (a trailing
`<span>`), never the actual paragraphs/lists that follow the wrapper as its
siblings. This silently broke wiki-chunk ingestion for every destination
(confirmed live: the wiki Qdrant collection had 0 points across all
destinations before this fix), which in turn disabled the "wiki" fallback
verification path in services/poi_pinning.py for every destination.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from scrapers.wikivoyage import scrape_wikivoyage

NEW_MARKUP = """
<html><body>
<div class="mw-heading mw-heading2"><h2 id="See">See</h2></div>
<p>The British Museum houses an enormous collection of world artifacts spanning two million years of human history and culture, drawing millions of visitors annually.</p>
<ul><li>Tower of London is a historic castle on the Thames, famous for housing the Crown Jewels and centuries of royal history.</li></ul>
<div class="mw-heading mw-heading2"><h2 id="Eat">Eat</h2></div>
<p>Borough Market is a popular food market near London Bridge, offering fresh produce, artisan cheeses, and street food from vendors across the city.</p>
<div class="mw-heading mw-heading2"><h2 id="Go_next">Go next</h2></div>
<p>Consider a day trip to Oxford or Cambridge, both easily reachable by train and offering centuries of academic history to explore.</p>
</body></html>
"""

OLD_MARKUP = """
<html><body>
<h2 id="See">See</h2>
<p>The British Museum houses an enormous collection of world artifacts spanning two million years of human history and culture, drawing millions of visitors annually.</p>
<ul><li>Tower of London is a historic castle on the Thames, famous for housing the Crown Jewels and centuries of royal history.</li></ul>
<h2 id="Eat">Eat</h2>
<p>Borough Market is a popular food market near London Bridge, offering fresh produce, artisan cheeses, and street food from vendors across the city.</p>
</body></html>
"""


def _mock_response(html: str):
    resp = AsyncMock()
    resp.text = html
    resp.raise_for_status = lambda: None
    return resp


class TestScrapeWikivoyage:
    @pytest.mark.asyncio
    async def test_extracts_content_from_mw_heading_wrapped_markup(self):
        """Current MediaWiki skin: <h2> wrapped in <div class="mw-heading">."""
        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(return_value=_mock_response(NEW_MARKUP))
            docs = await scrape_wikivoyage("London")

        assert docs, "expected non-empty docs from mw-heading-wrapped markup"
        sections = {d["section"] for d in docs}
        assert "see" in sections
        assert "eat" in sections
        blob = " ".join(d["text"] for d in docs)
        assert "British Museum" in blob
        assert "Borough Market" in blob

    @pytest.mark.asyncio
    async def test_extracts_content_from_legacy_markup(self):
        """Older/other skins: <h2> is a direct sibling of section content."""
        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(return_value=_mock_response(OLD_MARKUP))
            docs = await scrape_wikivoyage("London")

        assert docs, "expected non-empty docs from legacy markup"
        blob = " ".join(d["text"] for d in docs)
        assert "British Museum" in blob
        assert "Borough Market" in blob

    @pytest.mark.asyncio
    async def test_section_stops_at_next_heading_wrapper(self):
        """Content from one section must not bleed into the next section."""
        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(return_value=_mock_response(NEW_MARKUP))
            docs = await scrape_wikivoyage("London")

        see_docs = [d for d in docs if d["section"] == "see"]
        eat_docs = [d for d in docs if d["section"] == "eat"]
        assert see_docs and "Borough Market" not in " ".join(d["text"] for d in see_docs)
        assert eat_docs and "British Museum" not in " ".join(d["text"] for d in eat_docs)
