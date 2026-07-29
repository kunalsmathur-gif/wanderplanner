"""Unit tests for the entry/visa corpus (issue #37) — scraper, retrieval and
the wizard gate. Fully offline: no network, no Qdrant, no embeddings.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config import settings
from scrapers.visa_info import VISA_SEED_COUNTRIES, _parse_entry_sections

COUNTRY_MARKUP = """
<html><body>
<div class="mw-heading mw-heading2"><h2 id="Get_in">Get in</h2></div>
<p>Most visitors require a visa to enter, and applications are made online through the official e-visa portal at least four days before travel.</p>
<div class="mw-heading mw-heading3"><h3 id="Entry_requirements">Entry requirements</h3></div>
<p>Your passport must be valid for at least six months beyond the date of arrival, and you will need proof of onward travel at immigration.</p>
<div class="mw-heading mw-heading2"><h2 id="Get_around">Get around</h2></div>
<p>Trains connect all the major cities and are comfortable, punctual and considerably cheaper than flying between regional airports.</p>
</body></html>
"""

# A "Get in" section that is entirely about transport, which is the common case
# for city guides — none of it should survive the visa filter.
TRANSPORT_ONLY_MARKUP = """
<html><body>
<div class="mw-heading mw-heading2"><h2 id="Get_in">Get in</h2></div>
<p>The airport is twenty kilometres north of the centre and taxis into town take about forty minutes depending on the traffic that day.</p>
<p>Long distance coaches arrive at the central bus station, which is a ten minute walk from the main railway terminus and the metro.</p>
</body></html>
"""


class TestParseEntrySections:
    def test_extracts_visa_chunks_from_get_in_and_subsections(self):
        docs = _parse_entry_sections(COUNTRY_MARKUP, "Thailand", "https://en.wikivoyage.org/wiki/Thailand")
        assert docs, "expected entry-rule chunks"
        joined = " ".join(d["text"] for d in docs)
        assert "e-visa portal" in joined
        # The H3 subsection under Get in must be included, not cut off.
        assert "six months beyond the date of arrival" in joined

    def test_stops_at_the_next_h2(self):
        docs = _parse_entry_sections(COUNTRY_MARKUP, "Thailand", "u")
        joined = " ".join(d["text"] for d in docs)
        assert "Trains connect all the major cities" not in joined

    def test_transport_only_get_in_yields_nothing(self):
        """"Get in" is shared with flights/buses; only entry-rule text counts."""
        assert _parse_entry_sections(TRANSPORT_ONLY_MARKUP, "Nowhere", "u") == []

    def test_destination_is_the_country(self):
        docs = _parse_entry_sections(COUNTRY_MARKUP, "Thailand", "u")
        assert {d["destination"] for d in docs} == {"Thailand"}
        assert {d["country"] for d in docs} == {"Thailand"}

    def test_payload_uses_the_unified_schema(self):
        doc = _parse_entry_sections(COUNTRY_MARKUP, "Thailand", "u")[0]
        assert doc["source"] == "visa_info"
        assert doc["content_type"] == "guide"
        assert doc["source_name"] == "Wikivoyage"
        assert "ingested_at" in doc

    def test_mediawiki_edit_markers_are_stripped(self):
        """`get_text()` over a section that contains subsection headings pulls
        in MediaWiki's per-heading "[edit]" link. Found by reading the live
        France/UAE output, not by a failing count — these chunks are both
        embedded and surfaced into the wizard prompt."""
        markup = """
        <html><body>
        <div class="mw-heading mw-heading2"><h2 id="Get_in">Get in</h2></div>
        <p>Entry requirements [ edit ] Minimum validity of travel documents is three months beyond your intended departure date from the Schengen area.</p>
        </body></html>
        """
        docs = _parse_entry_sections(markup, "France", "u")
        assert docs
        assert "edit" not in " ".join(d["text"] for d in docs).lower()

    def test_visa_keyword_does_not_match_visakhapatnam(self):
        """The bug class this repo has hit five times (v10.40.4/5/6): "visa" as
        a bare substring matches "Visakhapatnam", a real Indian city. Whole-word
        matching is what keeps a transport paragraph out of the visa corpus."""
        markup = """
        <html><body>
        <div class="mw-heading mw-heading2"><h2 id="Get_in">Get in</h2></div>
        <p>Direct overnight trains run from Visakhapatnam and take around eleven hours, arriving early in the morning at the central station downtown.</p>
        </body></html>
        """
        assert _parse_entry_sections(markup, "India", "u") == []


class TestSeedCountries:
    def test_india_is_present_and_first(self):
        """India-first is deliberate — it is both the home market and the
        largest inbound destination this product serves."""
        assert VISA_SEED_COUNTRIES[0] == "India"

    def test_no_duplicates(self):
        assert len(VISA_SEED_COUNTRIES) == len(set(VISA_SEED_COUNTRIES))


def _hit(text: str, score: float, url: str = "https://en.wikivoyage.org/wiki/Thailand"):
    h = MagicMock()
    h.score = score
    h.payload = {"text": text, "source_url": url}
    return h


class TestRetrieveVisaNote:
    @pytest.mark.asyncio
    async def test_returns_empty_when_disabled(self, monkeypatch):
        from services.visa import retrieve_visa_note

        monkeypatch.setattr(settings, "visa_info_retrieval_enabled", False)
        assert await retrieve_visa_note("Thailand") == ""

    @pytest.mark.asyncio
    async def test_returns_empty_for_blank_country(self):
        from services.visa import retrieve_visa_note

        assert await retrieve_visa_note("  ") == ""

    @pytest.mark.asyncio
    async def test_builds_attributed_note_from_hits(self, monkeypatch):
        from services.visa import retrieve_visa_note

        monkeypatch.setattr(settings, "visa_info_retrieval_enabled", True)
        client = MagicMock()
        client.search.return_value = [_hit("Most visitors need an e-visa.", 0.8)]
        with patch("services.visa.embed", return_value=[[0.1] * 384]), \
             patch("services.visa.get_qdrant", return_value=client):
            note = await retrieve_visa_note("Thailand")

        assert "Most visitors need an e-visa." in note
        assert "Thailand" in note
        # Attribution and the caveat are not optional garnish — see the module
        # docstring on why this is never stated as a determination.
        assert "https://en.wikivoyage.org/wiki/Thailand" in note
        assert "official immigration site" in note

    @pytest.mark.asyncio
    async def test_low_scoring_hits_are_dropped(self, monkeypatch):
        from services.visa import retrieve_visa_note

        monkeypatch.setattr(settings, "visa_info_retrieval_enabled", True)
        client = MagicMock()
        client.search.return_value = [_hit("Unrelated waffle.", 0.05)]
        with patch("services.visa.embed", return_value=[[0.1] * 384]), \
             patch("services.visa.get_qdrant", return_value=client):
            assert await retrieve_visa_note("Thailand") == ""

    @pytest.mark.asyncio
    async def test_retrieval_failure_degrades_to_silence(self, monkeypatch):
        """A visa lookup must never take down a wizard turn."""
        from services.visa import retrieve_visa_note

        monkeypatch.setattr(settings, "visa_info_retrieval_enabled", True)
        with patch("services.visa.embed", side_effect=Exception("qdrant down")):
            assert await retrieve_visa_note("Thailand") == ""


class TestWizardVisaGate:
    """The hint is gated on the user asking. An unconditional lookup would put
    an embedding + Qdrant round-trip on every wizard turn's critical path."""

    @pytest.mark.asyncio
    async def test_no_lookup_when_user_is_not_asking_about_visas(self):
        from chains.wizard_chat_chain import _visa_hint_for

        with patch("services.visa.retrieve_visa_note", new=AsyncMock()) as mock_retrieve:
            hint = await _visa_hint_for(
                {"destination": {"city": "Bangkok", "country": "Thailand"}},
                "I want to go in December for a week",
            )
        assert hint == ""
        mock_retrieve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_looks_up_when_user_asks(self):
        from chains.wizard_chat_chain import _visa_hint_for

        with patch("services.visa.retrieve_visa_note", new=AsyncMock(return_value="NOTE")) as mock_retrieve:
            hint = await _visa_hint_for(
                {"destination": {"city": "Bangkok", "country": "Thailand"}},
                "do I need a visa for this trip?",
            )
        assert hint == "NOTE"
        assert mock_retrieve.await_args.args[0] == "Thailand"

    @pytest.mark.asyncio
    async def test_no_country_collected_yet_returns_empty(self):
        from chains.wizard_chat_chain import _visa_hint_for

        with patch("services.visa.retrieve_visa_note", new=AsyncMock()) as mock_retrieve:
            hint = await _visa_hint_for({"destination": {"city": "Bangkok"}}, "do I need a visa?")
        assert hint == ""
        mock_retrieve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_falls_back_to_destination_country_field(self):
        """`destination_mode == "country"` puts the country here instead."""
        from chains.wizard_chat_chain import _visa_hint_for

        with patch("services.visa.retrieve_visa_note", new=AsyncMock(return_value="NOTE")) as mock_retrieve:
            hint = await _visa_hint_for({"destination_country": "Japan"}, "visa rules?")
        assert hint == "NOTE"
        assert mock_retrieve.await_args.args[0] == "Japan"
