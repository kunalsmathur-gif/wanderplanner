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

from core.config import settings
from scrapers.wikivoyage import WIKIVOYAGE_TITLE_OVERRIDES, scrape_wikivoyage

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


@pytest.fixture(autouse=True)
def _districts_disabled_by_default(monkeypatch):
    """District sub-article scraping (issue #45) adds an `allpages` API call
    plus N article fetches to every *successful* scrape.

    Every test in this module predates it and asserts on either the
    last-requested URL or an exact `await_count`, so both would now describe
    the district traffic rather than the thing under test. Turning it off here
    keeps each of those tests about one thing; `TestDistrictSubpages` below
    switches it back on explicitly, so the behaviour is still covered.
    """
    monkeypatch.setattr(settings, "wikivoyage_max_district_subpages", 0)


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


DISTRICT_MARKUP = """
<html><body>
<div class="mw-heading mw-heading2"><h2 id="Eat">Eat</h2></div>
<p>Chez Michel is a classic neighbourhood bistro serving a three-course prix fixe menu for 34 euros, with regional cheeses and an all-French wine list.</p>
<div class="mw-heading mw-heading2"><h2 id="Sleep">Sleep</h2></div>
<p>Hotel du Nord offers simple double rooms from 95 euros a night including breakfast, a short walk from the canal and the metro.</p>
</body></html>
"""


class TestDistrictSubpages:
    """Issue #45 — hub-city guides delegate their priced Eat/Sleep listings to
    per-district sub-articles.

    🔴 **The issue proposed detecting these by parsing links out of the guide's
    "Districts" section. Measured live 2026-07-29, that finds nothing:**
    Paris/Bangkok/Tokyo/London render **zero** `/wiki/<City>/<District>` hrefs
    and their Districts sections contain only `Special:Map` links. The
    sub-pages exist regardless (Paris 21 non-redirect, Tokyo 29), so discovery
    goes through `list=allpages&apprefix=`. A link-parsing build would have
    passed a hand-written fixture and silently ingested nothing in production,
    so the mechanism is pinned by `test_discovery_uses_allpages_not_link_parsing`.
    """

    @staticmethod
    def _routed_client(district_titles, city="Paris", failing=()):
        """Route by URL: the API endpoint answers `allpages`, `<city>/<x>`
        answers district markup, anything else answers the parent guide."""
        calls: list[str] = []

        async def _get(url, **kwargs):
            calls.append(url)
            if url == "https://en.wikivoyage.org/w/api.php":
                params = kwargs.get("params") or {}
                if params.get("list") == "allpages":
                    return _mock_json_response(
                        {"query": {"allpages": [{"title": t} for t in district_titles]}}
                    )
                return _mock_json_response({"query": {"pages": {"1": {"pageprops": {}}}}})
            if f"/wiki/{city}_" in url or f"/wiki/{city}/" in url:
                if any(f.replace(" ", "_") in url for f in failing):
                    raise Exception("504 district timeout")
                return _mock_response(DISTRICT_MARKUP)
            return _mock_response(NEW_MARKUP)

        return AsyncMock(side_effect=_get), calls

    @pytest.mark.asyncio
    async def test_hub_city_merges_district_chunks_under_parent_destination(self, monkeypatch):
        monkeypatch.setattr(settings, "wikivoyage_max_district_subpages", 8)
        titles = ["Paris/11th arrondissement", "Paris/12th arrondissement"]
        getter, _calls = self._routed_client(titles)

        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls, \
             patch("scrapers.wikivoyage.asyncio.sleep", new=AsyncMock()):
            mock_client_cls.return_value.__aenter__.return_value.get = getter
            docs = await scrape_wikivoyage("Paris")

        district_docs = [d for d in docs if d.get("district")]
        assert district_docs, "expected chunks from the district sub-articles"
        # Everything stays retrievable under the parent city, not "Paris/11th…".
        assert {d["destination"] for d in docs} == {"Paris"}
        assert {d["district"] for d in district_docs} == {
            "11th arrondissement", "12th arrondissement",
        }
        # The parent's own chunks are still there and carry no district tag.
        assert any("district" not in d for d in docs)

    @pytest.mark.asyncio
    async def test_non_hub_city_fetches_no_extra_articles(self, monkeypatch):
        """Acceptance criterion: existing single-article destinations must be
        unaffected — no unnecessary extra fetches."""
        monkeypatch.setattr(settings, "wikivoyage_max_district_subpages", 8)
        getter, calls = self._routed_client([], city="Jaipur")

        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls, \
             patch("scrapers.wikivoyage.asyncio.sleep", new=AsyncMock()):
            mock_client_cls.return_value.__aenter__.return_value.get = getter
            docs = await scrape_wikivoyage("Jaipur")

        assert docs, "parent article should still be scraped"
        assert not any(d.get("district") for d in docs)
        article_fetches = [c for c in calls if "/w/api.php" not in c]
        assert len(article_fetches) == 1, f"expected only the parent fetch, got {article_fetches}"

    @pytest.mark.asyncio
    async def test_discovery_uses_allpages_not_link_parsing(self, monkeypatch):
        """Pins the mechanism, including the redirect filter — Wikivoyage
        aliases districts heavily (Paris/10th -> Paris/10th arrondissement,
        three spellings of Bangkok/Banglamphu), so unfiltered enumeration
        would fetch, embed and store the same district repeatedly."""
        monkeypatch.setattr(settings, "wikivoyage_max_district_subpages", 8)
        getter, _calls = self._routed_client(["Paris/11th arrondissement"])

        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls, \
             patch("scrapers.wikivoyage.asyncio.sleep", new=AsyncMock()):
            mock_client_cls.return_value.__aenter__.return_value.get = getter
            await scrape_wikivoyage("Paris")

        allpages_calls = [
            kw["params"] for _a, kw in getter.await_args_list
            if (kw.get("params") or {}).get("list") == "allpages"
        ]
        assert allpages_calls, "district discovery must go through list=allpages"
        params = allpages_calls[0]
        assert params["apprefix"] == "Paris/"
        assert params["apfilterredir"] == "nonredirects"
        assert params["apnamespace"] == "0"

    @pytest.mark.asyncio
    async def test_cap_limits_districts_fetched(self, monkeypatch):
        monkeypatch.setattr(settings, "wikivoyage_max_district_subpages", 2)
        titles = [f"Paris/{n}th arrondissement" for n in range(10, 20)]
        getter, calls = self._routed_client(titles)

        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls, \
             patch("scrapers.wikivoyage.asyncio.sleep", new=AsyncMock()):
            mock_client_cls.return_value.__aenter__.return_value.get = getter
            await scrape_wikivoyage("Paris")

        district_fetches = [c for c in calls if "/wiki/Paris/" in c]
        assert len(district_fetches) == 2

    @pytest.mark.asyncio
    async def test_zero_cap_disables_district_scraping_entirely(self, monkeypatch):
        monkeypatch.setattr(settings, "wikivoyage_max_district_subpages", 0)
        getter, calls = self._routed_client(["Paris/11th arrondissement"])

        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls, \
             patch("scrapers.wikivoyage.asyncio.sleep", new=AsyncMock()):
            mock_client_cls.return_value.__aenter__.return_value.get = getter
            docs = await scrape_wikivoyage("Paris")

        assert not any(d.get("district") for d in docs)
        assert not [c for c in calls if "/w/api.php" in c], "must not even discover when disabled"

    @pytest.mark.asyncio
    async def test_one_failing_district_does_not_discard_the_others(self, monkeypatch):
        """Same best-effort contract as the rest of this module: a single 504
        must not throw away districts already collected, nor the parent's
        chunks. Same shape as the v10.38.0 `return_exceptions` bug, where one
        raising source discarded an already-successful sibling."""
        monkeypatch.setattr(settings, "wikivoyage_max_district_subpages", 8)
        titles = ["Paris/11th arrondissement", "Paris/12th arrondissement"]
        getter, _calls = self._routed_client(titles, failing=["Paris/11th arrondissement"])

        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls, \
             patch("scrapers.wikivoyage.asyncio.sleep", new=AsyncMock()):
            mock_client_cls.return_value.__aenter__.return_value.get = getter
            docs = await scrape_wikivoyage("Paris")

        districts = {d["district"] for d in docs if d.get("district")}
        assert districts == {"12th arrondissement"}
        assert any("district" not in d for d in docs), "parent chunks must survive"

    @pytest.mark.asyncio
    async def test_discovery_failure_leaves_parent_chunks_intact(self, monkeypatch):
        monkeypatch.setattr(settings, "wikivoyage_max_district_subpages", 8)

        async def _get(url, **kwargs):
            if url == "https://en.wikivoyage.org/w/api.php":
                raise Exception("API down")
            return _mock_response(NEW_MARKUP)

        with patch("scrapers.wikivoyage.httpx.AsyncClient") as mock_client_cls, \
             patch("scrapers.wikivoyage.asyncio.sleep", new=AsyncMock()):
            mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(side_effect=_get)
            docs = await scrape_wikivoyage("Paris")

        assert docs, "a failed district discovery must not lose the parent article"
        assert not any(d.get("district") for d in docs)
