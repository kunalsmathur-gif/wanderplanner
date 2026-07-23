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

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scrapers.wikivoyage import scrape_wikivoyage, WIKIVOYAGE_TITLE_OVERRIDES

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


class TestWikivoyageTitleOverride:
    """"New York" -> /wiki/New_York is the STATE-level Wikivoyage article
    (region/city index, no See/Do/Eat sections) — a *different real page*
    from the city guide at /wiki/New_York_City, not a 404. Live-confirmed
    2026-07-20: the naive slug fetch returns 200 with zero usable chunks
    (no matching section headings) rather than an obvious error."""

    @pytest.mark.asyncio
    async def test_overridden_destination_uses_mapped_slug(self):
        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(return_value=_mock_response(NEW_MARKUP))
            await scrape_wikivoyage("New York")

        requested_url = mock_client.get.await_args.args[0]
        assert requested_url == "https://en.wikivoyage.org/wiki/New_York_City"

    @pytest.mark.asyncio
    async def test_non_overridden_destination_unaffected(self):
        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(return_value=_mock_response(NEW_MARKUP))
            await scrape_wikivoyage("London")

        requested_url = mock_client.get.await_args.args[0]
        assert requested_url == "https://en.wikivoyage.org/wiki/London"

    def test_override_keys_are_lowercase(self):
        assert all(k == k.lower() for k in WIKIVOYAGE_TITLE_OVERRIDES)


class TestScrapeWikivoyageRetry:
    """wikivoyage.org occasionally returns transient failures (rate-limiting,
    brief 5xx) that resolve seconds later — found live 2026-07-20 during
    re-ingestion testing. Retrying with backoff avoids silently recording a
    destination as having zero wiki chunks."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_after_exhausting_retries(self):
        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls, \
             patch("scrapers.wikivoyage.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(side_effect=Exception("timeout"))
            docs = await scrape_wikivoyage("Nowhere")

        assert docs == []
        assert mock_client.get.await_count == 3
        assert mock_sleep.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_transient_failure_then_succeeds(self):
        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls, \
             patch("scrapers.wikivoyage.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(side_effect=[Exception("503"), _mock_response(NEW_MARKUP)])
            docs = await scrape_wikivoyage("London")

        assert docs, "expected docs after the transient failure resolved"
        assert mock_client.get.await_count == 2
        assert mock_sleep.await_count == 1


class TestIngestWikivoyageOrphanCleanup:
    """ingest_wikivoyage() must delete-then-upsert per destination — the
    same orphan-accumulation risk as scrapers/osm.py applies here since
    chunk boundaries can shift between scraper-logic revisions."""

    @pytest.mark.asyncio
    async def test_deletes_stale_points_before_upserting_new_ones(self):
        from scrapers.wikivoyage import ingest_wikivoyage

        fake_docs = [
            {"destination": "London", "source": "wikivoyage", "section": "see",
             "text": "The British Museum is free to enter.", "source_url": "https://en.wikivoyage.org/wiki/London"},
        ]
        mock_qdrant = MagicMock()

        with patch("scrapers.wikivoyage.scrape_wikivoyage", new=AsyncMock(return_value=fake_docs)), \
             patch("scrapers.wikivoyage.embed", return_value=[[0.1] * 384]), \
             patch("scrapers.wikivoyage.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.wikivoyage.delete_stale_destination_points", return_value=3) as mock_delete:
            count = await ingest_wikivoyage("London")

        assert count == 1
        mock_delete.assert_called_once()
        args, _ = mock_delete.call_args
        assert args[0] is mock_qdrant
        assert args[2] == "London"
        mock_qdrant.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_cleanup_call_when_scrape_returns_nothing(self):
        from scrapers.wikivoyage import ingest_wikivoyage

        with patch("scrapers.wikivoyage.scrape_wikivoyage", new=AsyncMock(return_value=[])), \
             patch("scrapers.wikivoyage.delete_stale_destination_points") as mock_delete:
            count = await ingest_wikivoyage("Nowhere")

        assert count == 0
        mock_delete.assert_not_called()


def _mock_json_response(payload: dict, status_code: int = 200):
    resp = AsyncMock()
    resp.status_code = status_code
    resp.json = lambda: payload
    if status_code >= 400:
        resp.raise_for_status = MagicMock(side_effect=Exception(f"{status_code} error"))
    else:
        resp.raise_for_status = lambda: None
    return resp


class TestWikivoyage404SearchFallback:
    """A naive `.title()` slug can 404 even for a real destination — e.g.
    "Washington DC" -> "Washington_Dc", "Rio de Janeiro" -> "Rio_De_Janeiro"
    (Python's `.title()` mis-cases "DC"/"de"). Rather than hand-pinning every
    such casing mismatch, fall back to Wikivoyage's own fuzzy search."""

    @pytest.mark.asyncio
    async def test_404_falls_back_to_wikivoyage_search_result(self):
        get_responses = [
            _mock_json_response({}, status_code=404),  # naive slug 404s
            _mock_response(NEW_MARKUP),  # fetch of the search-resolved title
        ]
        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls, \
             patch(
                 "scrapers.wikivoyage._wikivoyage_search_title",
                 new=AsyncMock(return_value="Washington, D.C."),
             ):
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(side_effect=get_responses)
            docs = await scrape_wikivoyage("Washington DC")

        assert docs
        last_url = mock_client.get.await_args_list[-1].args[0]
        assert last_url == "https://en.wikivoyage.org/wiki/Washington,_D.C."


class TestWikivoyageDisambiguation:
    """Some destination names are genuine Wikivoyage disambiguation pages
    (e.g. "Queenstown", "Oaxaca", "Cartagena") rather than a single city
    guide — the naive fetch succeeds (200) but yields zero usable chunks,
    the same failure mode as the New York state-vs-city override."""

    @pytest.mark.asyncio
    async def test_disambiguation_page_resolved_via_country_match(self):
        from models.common import GeocodeResponse

        disambig_page = """
        <html><body><div id="mw-content-text">
        <a href="/wiki/Cartagena_(Colombia)">Cartagena (Colombia)</a>
        <a href="/wiki/Cartagena_(Spain)">Cartagena (Spain)</a>
        </div></body></html>
        """
        get_responses = [
            _mock_response("<html><body><h2 id='mw-toc-heading'></h2></body></html>"),  # naive fetch: disambig, 0 docs
            _mock_json_response({"query": {"pages": {"1": {"pageprops": {"disambiguation": ""}}}}}),  # pageprops
            _mock_response(disambig_page),  # disambiguation page itself
            _mock_response(NEW_MARKUP),  # final resolved city page
        ]
        fake_geo = GeocodeResponse(display_name="Cartagena, Colombia", lat=10.4, lon=-75.5, country_code="co")

        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls, \
             patch("scrapers.wikivoyage.geocode_city", new=AsyncMock(return_value=fake_geo)):
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(side_effect=get_responses)
            docs = await scrape_wikivoyage("Cartagena")

        assert docs
        last_url = mock_client.get.await_args_list[-1].args[0]
        assert last_url == "https://en.wikivoyage.org/wiki/Cartagena_(Colombia)"

    @pytest.mark.asyncio
    async def test_disambiguation_prefers_city_over_region_when_country_ties(self):
        """"Oaxaca (state)" vs "Oaxaca (city)" both sit under Mexico, so a
        country match alone can't break the tie — must prefer the
        non-region-level candidate."""
        from models.common import GeocodeResponse

        disambig_page = """
        <html><body><div id="mw-content-text">
        <a href="/wiki/Oaxaca_(state)">Oaxaca (state)</a>
        <a href="/wiki/Oaxaca_(city)">Oaxaca (city)</a>
        </div></body></html>
        """
        get_responses = [
            _mock_response("<html><body><h2 id='mw-toc-heading'></h2></body></html>"),
            _mock_json_response({"query": {"pages": {"1": {"pageprops": {"disambiguation": ""}}}}}),
            _mock_response(disambig_page),
            _mock_response(NEW_MARKUP),
        ]
        fake_geo = GeocodeResponse(display_name="Oaxaca, Mexico", lat=17.0, lon=-96.5, country_code="mx")

        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls, \
             patch("scrapers.wikivoyage.geocode_city", new=AsyncMock(return_value=fake_geo)):
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(side_effect=get_responses)
            await scrape_wikivoyage("Oaxaca")

        last_url = mock_client.get.await_args_list[-1].args[0]
        assert last_url == "https://en.wikivoyage.org/wiki/Oaxaca_(city)"

    @pytest.mark.asyncio
    async def test_non_disambiguation_zero_docs_page_returns_empty_without_extra_calls(self):
        """A genuinely empty/structurally-different page that isn't a
        disambiguation page (pageprops has no `disambiguation` key) should
        just return an empty list, not loop forever trying to disambiguate."""
        get_responses = [
            _mock_response("<html><body><h2 id='mw-toc-heading'></h2></body></html>"),
            _mock_json_response({"query": {"pages": {"1": {"pageprops": {}}}}}),
        ]
        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.get = AsyncMock(side_effect=get_responses)
            docs = await scrape_wikivoyage("Somewhere")

        assert docs == []
