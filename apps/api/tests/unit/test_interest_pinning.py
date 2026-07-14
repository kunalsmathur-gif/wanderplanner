"""
Unit tests for the refinement hard-constraints pipeline ("Harry Potter test",
docs/GTM_STRATEGY.md §2): interest expansion (mock mode), OSM/wiki candidate
verification, pin merging, the PINNED prompt block, and the chat_refine
orchestration. Qdrant + LLM calls are mocked — fully offline.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from chains.chat_refine_chain import (
    ChatRefineRequest,
    ChatRefineResponse,
    _apply_interest_pinning,
    _is_transient_llm_error,
    chat_refine,
)
from chains.interest_expansion_chain import expand_interest_to_candidates, _mock_candidates
from chains.itinerary_chain import (
    _classify_gemini_error,
    _enforce_pins,
    _mock_itinerary,
    _pinned_guidance_block,
)
from models.chat import ChatMessage
from models.itinerary import ItineraryDay, ItineraryItem, ItineraryItemLocation
from models.trip import MAX_PINNED_POIS, DestinationInput, PinnedPOI, TripConfig
from services.poi_pinning import (
    _names_match,
    _normalize,
    merge_pins,
    verify_candidates_sync,
)


def _trip(pins: list[PinnedPOI] | None = None) -> TripConfig:
    return TripConfig(
        destination=DestinationInput(city="London", country="UK", lat=51.5, lon=-0.12),
        pinned_pois=pins or [],
    )


def _poi(name: str, lat: float = 51.69, lon: float = -0.42, poi_type: str = "attraction") -> dict:
    return {"destination": "London", "name": name, "poi_type": poi_type, "lat": lat, "lon": lon}


def _wiki_chunk(text: str) -> dict:
    return {"destination": "London", "text": text}


def _mock_qdrant(pois: list[dict], wiki_chunks: list[dict]) -> MagicMock:
    client = MagicMock()

    def _scroll(collection_name, scroll_filter, limit, with_payload, with_vectors):
        payloads = pois if collection_name == "osm_pois" else wiki_chunks
        points = []
        for p in payloads:
            pt = MagicMock()
            pt.payload = p
            points.append(pt)
        return points, None

    client.scroll.side_effect = _scroll
    return client


class TestNameMatching:
    def test_normalize_strips_punctuation_and_case(self):
        assert _normalize("Warner Bros. Studio Tour!") == "warner bros studio tour"

    def test_exact_match(self):
        assert _names_match("leadenhall market", "leadenhall market")

    def test_containment_match(self):
        assert _names_match(
            _normalize("Warner Bros. Studio Tour"),
            _normalize("Warner Bros. Studio Tour London"),
        )

    def test_fuzzy_match_small_variation(self):
        assert _names_match(
            _normalize("Kings Cross Station"),
            _normalize("King's Cross station"),
        )

    def test_different_places_do_not_match(self):
        assert not _names_match(_normalize("Leadenhall Market"), _normalize("Borough Market"))

    def test_short_candidate_needs_exact(self):
        # containment shortcut requires ≥6 chars — "eye" ⊂ "london eye" must not match
        assert not _names_match("eye", "london eye")

    # Diacritic folding — live 2026-07-13 eval suspects: a Gemini candidate
    # like "Ryōan-ji" must match the ASCII OSM fixture name exactly, not
    # merely survive on fuzzy ratio.
    def test_normalize_folds_diacritics(self):
        assert _normalize("Ryōan-ji") == "ryoan ji"
        assert _normalize("Sé Cathedral") == "se cathedral"
        assert _normalize("Sagrada Família") == "sagrada familia"

    def test_diacritic_candidate_matches_ascii_name(self):
        assert _names_match(_normalize("Ryōan-ji"), _normalize("Ryoan-ji"))
        assert _names_match(_normalize("Sé Cathedral"), _normalize("Se Cathedral"))
        assert _names_match(_normalize("Sagrada Família"), _normalize("Sagrada Familia"))


class TestVerifyCandidates:
    def _run(self, candidates, pois, wiki_chunks=None):
        with patch("services.poi_pinning.get_qdrant", return_value=_mock_qdrant(pois, wiki_chunks or [])):
            return verify_candidates_sync(candidates, "London", source_interest="Harry Potter")

    def test_osm_match_gets_real_coordinates(self):
        pins, dropped = self._run(
            ["Warner Bros. Studio Tour"],
            [_poi("Warner Bros. Studio Tour London", lat=51.69, lon=-0.42)],
        )
        assert dropped == []
        assert len(pins) == 1
        assert pins[0].verified_by == "osm"
        assert pins[0].lat == 51.69
        assert pins[0].name == "Warner Bros. Studio Tour London"  # canonical OSM name wins
        assert pins[0].source_interest == "Harry Potter"

    def test_unverified_candidate_dropped(self):
        pins, dropped = self._run(["Hogwarts Castle Scotland"], [_poi("Leadenhall Market")])
        assert pins == []
        assert dropped == ["Hogwarts Castle Scotland"]

    def test_wiki_fallback_confirms_existence_without_coords(self):
        pins, dropped = self._run(
            ["Leadenhall Market"],
            [],  # not in OSM
            [_wiki_chunk("The Victorian Leadenhall Market appeared in the films.")],
        )
        assert dropped == []
        assert len(pins) == 1
        assert pins[0].verified_by == "wiki"
        assert pins[0].lat == 0.0

    def test_osm_preferred_over_wiki(self):
        pins, _ = self._run(
            ["Leadenhall Market"],
            [_poi("Leadenhall Market")],
            [_wiki_chunk("Leadenhall Market is lovely")],
        )
        assert pins[0].verified_by == "osm"

    def test_duplicate_candidates_deduped(self):
        pins, dropped = self._run(
            ["Leadenhall Market", "leadenhall market!"],
            [_poi("Leadenhall Market")],
        )
        assert len(pins) == 1
        assert dropped == []

    def test_empty_inputs(self):
        assert verify_candidates_sync([], "London") == ([], [])
        pins, dropped = verify_candidates_sync(["X Place"], "")
        assert pins == [] and dropped == ["X Place"]

    def test_diacritic_candidate_verified_against_ascii_fixture(self):
        pins, dropped = self._run(["Ryōan-ji"], [_poi("Ryoan-ji", poi_type="temple")])
        assert dropped == []
        assert len(pins) == 1
        assert pins[0].name == "Ryoan-ji"  # canonical OSM name wins
        assert pins[0].verified_by == "osm"

    def test_exact_match_beats_earlier_fuzzy_hit(self):
        # Live 2026-07-13: "Ginkaku-ji" fuzzy-matched "Kinkaku-ji" (ratio
        # 0.89) sitting earlier in the index than its own exact entry.
        pins, dropped = self._run(
            ["Ginkaku-ji"],
            [_poi("Kinkaku-ji", poi_type="temple"), _poi("Ginkaku-ji", poi_type="temple")],
        )
        assert dropped == []
        assert [p.name for p in pins] == ["Ginkaku-ji"]


class TestMergePins:
    def _pin(self, name: str) -> PinnedPOI:
        return PinnedPOI(name=name)

    def test_existing_first_and_deduped(self):
        merged = merge_pins(
            [self._pin("Leadenhall Market")],
            [self._pin("leadenhall market"), self._pin("Platform 9 3/4")],
        )
        assert [p.name for p in merged] == ["Leadenhall Market", "Platform 9 3/4"]

    def test_capped_at_max(self):
        merged = merge_pins(
            [self._pin(f"Existing Place {i}") for i in range(6)],
            [self._pin(f"New Place {i}") for i in range(6)],
        )
        assert len(merged) == MAX_PINNED_POIS
        assert merged[0].name == "Existing Place 0"  # existing commitments stable


class TestPinnedGuidanceBlock:
    def test_empty_pins_empty_block(self):
        assert _pinned_guidance_block(_trip()) == ""

    def test_osm_pin_includes_exact_coordinates(self):
        block = _pinned_guidance_block(_trip([
            PinnedPOI(name="Warner Bros. Studio Tour London", lat=51.69, lon=-0.42,
                      poi_type="attraction", source_interest="Harry Potter"),
        ]))
        assert "PINNED MUST-INCLUDE PLACES" in block
        assert "Warner Bros. Studio Tour London" in block
        assert "lat 51.69" in block
        assert "Harry Potter" in block

    def test_wiki_pin_flags_unknown_coordinates(self):
        block = _pinned_guidance_block(_trip([PinnedPOI(name="Leadenhall Market", verified_by="wiki")]))
        assert "coordinates not on file" in block


class TestInterestExpansionMockMode:
    def test_known_interest_returns_canned_candidates(self):
        assert "Warner Bros. Studio Tour London" in _mock_candidates("huge Harry Potter fan")

    def test_unknown_interest_returns_empty(self):
        assert _mock_candidates("competitive knitting") == []

    @pytest.mark.asyncio
    async def test_empty_args_short_circuit(self):
        assert await expand_interest_to_candidates("", "London") == []
        assert await expand_interest_to_candidates("Harry Potter", "") == []

    @pytest.mark.asyncio
    async def test_mock_provider_uses_canned_list(self):
        with patch("chains.interest_expansion_chain.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            out = await expand_interest_to_candidates("Harry Potter", "London")
        assert out == _mock_candidates("Harry Potter")


@pytest.mark.asyncio
class TestChatRefineOrchestration:
    async def _refine(self, message: str, trip: TripConfig, pins, dropped):
        async def _fake_verify(candidates, destination, source_interest=""):
            return pins, dropped

        with patch("chains.chat_refine_chain.settings") as refine_settings, \
             patch("chains.interest_expansion_chain.settings") as expand_settings, \
             patch("services.poi_pinning.verify_candidates", _fake_verify):
            refine_settings.llm_provider = "mock"
            expand_settings.llm_provider = "mock"
            return await chat_refine(ChatRefineRequest(
                messages=[ChatMessage(role="user", content=message)],
                trip_config=trip,
            ))

    async def test_named_interest_pins_verified_places(self):
        pin = PinnedPOI(name="Warner Bros. Studio Tour London", lat=51.69, lon=-0.42,
                        source_interest="Harry Potter")
        resp = await self._refine(
            "I'm a huge Harry Potter fan!", _trip(),
            pins=[pin], dropped=["Platform 9 3/4 King's Cross"],
        )
        assert resp.action_type == "patch_config"
        assert resp.named_interest == "Harry Potter"
        assert [p.name for p in resp.pinned_pois] == ["Warner Bros. Studio Tour London"]
        assert resp.dropped_candidates == ["Platform 9 3/4 King's Cross"]
        patch_pins = resp.config_patch["pinned_pois"]
        assert [p["name"] for p in patch_pins] == ["Warner Bros. Studio Tour London"]
        assert "📌" in resp.reply
        assert "couldn't verify" in resp.reply

    async def test_existing_pins_preserved_in_patch(self):
        existing = PinnedPOI(name="Leadenhall Market", verified_by="wiki")
        new_pin = PinnedPOI(name="Warner Bros. Studio Tour London")
        resp = await self._refine(
            "I'm a huge Harry Potter fan!", _trip([existing]),
            pins=[new_pin], dropped=[],
        )
        names = [p["name"] for p in resp.config_patch["pinned_pois"]]
        assert names == ["Leadenhall Market", "Warner Bros. Studio Tour London"]

    async def test_nothing_verified_is_reported_honestly(self):
        resp = await self._refine(
            "I'm a huge Harry Potter fan!", _trip(),
            pins=[], dropped=["Warner Bros. Studio Tour London"],
        )
        assert resp.pinned_pois == []
        assert resp.config_patch is None
        assert "haven't pinned anything" in resp.reply

    async def test_no_destination_skips_expansion(self):
        trip = TripConfig()  # no destination
        resp = await self._refine("I'm a huge Harry Potter fan!", trip, pins=[], dropped=[])
        assert resp.named_interest == "Harry Potter"
        assert resp.pinned_pois == []
        assert "📌" not in resp.reply

    async def test_non_interest_message_untouched(self):
        resp = await self._refine("make the pace more relaxed", _trip(),
                                  pins=[], dropped=[])
        assert resp.named_interest is None
        assert resp.config_patch == {"pace": "relaxed"}


class TestGeminiErrorClassifier:
    def test_503_is_transient(self):
        assert _classify_gemini_error("503 UNAVAILABLE high demand") == "transient"

    def test_retired_model_404_is_model_missing(self):
        err = ("404 NOT_FOUND. models/gemini-2.5-flash-lite-preview-06-17 "
               "is not found for API version v1beta")
        assert _classify_gemini_error(err) == "model_missing"

    def test_auth_error_is_fatal(self):
        assert _classify_gemini_error("401 UNAUTHENTICATED: API key not valid") == "fatal"


class TestTransientLLMErrorClassifier:
    def test_gemini_503_unavailable_is_transient(self):
        exc = RuntimeError("503 UNAVAILABLE. {'error': {'code': 503, 'status': 'UNAVAILABLE'}}")
        assert _is_transient_llm_error(exc)

    def test_quota_429_is_transient(self):
        assert _is_transient_llm_error(RuntimeError("429 RESOURCE_EXHAUSTED"))

    def test_bad_request_is_not_transient(self):
        assert not _is_transient_llm_error(ValueError("400 INVALID_ARGUMENT: bad schema"))
        assert not _is_transient_llm_error(RuntimeError("GEMINI_API_KEY is not set."))


class TestApplyInterestPinningGuards:
    @pytest.mark.asyncio
    async def test_no_interest_is_noop(self):
        resp = ChatRefineResponse(reply="hi", action_type="none")
        out = await _apply_interest_pinning(resp, _trip())
        assert out.reply == "hi"
        assert out.pinned_pois == []


@pytest.mark.asyncio
class TestThemesPatchBackstop:
    """Live 2026-07-13 eval regression (RF-004/RF-014): the refine LLM routed
    the interest into a themes config_patch and left named_interest null —
    the backstop must derive the interest from the NEW themes."""

    async def _apply(self, resp: ChatRefineResponse, trip: TripConfig,
                     pins: list[PinnedPOI]):
        expanded_with: list[str] = []

        async def _fake_expand(interest, destination):
            expanded_with.append(interest)
            return ["Ryoan-ji"] if pins else []

        async def _fake_verify(candidates, destination, source_interest=""):
            return pins, []

        with patch("chains.interest_expansion_chain.expand_interest_to_candidates",
                   _fake_expand), \
             patch("services.poi_pinning.verify_candidates", _fake_verify):
            out = await _apply_interest_pinning(resp, trip)
        return out, expanded_with

    async def test_new_theme_becomes_named_interest(self):
        resp = ChatRefineResponse(
            reply="Noted!", action_type="patch_config",
            config_patch={"themes": ["zen gardens", "temples"]},
        )
        pin = PinnedPOI(name="Ryoan-ji", lat=35.03, lon=135.72,
                        source_interest="zen gardens and temples")
        out, expanded_with = await self._apply(resp, _trip(), [pin])
        assert out.named_interest == "zen gardens and temples"
        assert expanded_with == ["zen gardens and temples"]
        assert [p.name for p in out.pinned_pois] == ["Ryoan-ji"]
        assert "📌" in out.reply

    async def test_themes_already_on_trip_do_not_retrigger(self):
        trip = _trip()
        trip = trip.model_copy(update={"themes": ["Zen Gardens"]})
        resp = ChatRefineResponse(
            reply="Noted!", action_type="patch_config",
            config_patch={"themes": ["zen gardens"]},  # case-insensitive dup
        )
        out, expanded_with = await self._apply(resp, trip, [])
        assert out.named_interest is None
        assert expanded_with == []
        assert out.pinned_pois == []

    async def test_explicit_named_interest_wins_over_backstop(self):
        resp = ChatRefineResponse(
            reply="On it!", action_type="patch_config",
            config_patch={"themes": ["street food"]},
            named_interest="Harry Potter",
        )
        out, expanded_with = await self._apply(resp, _trip(), [])
        assert out.named_interest == "Harry Potter"
        assert expanded_with == ["Harry Potter"]

    async def test_non_theme_patch_is_noop(self):
        resp = ChatRefineResponse(
            reply="Done!", action_type="patch_config",
            config_patch={"pace": "relaxed"},
        )
        out, expanded_with = await self._apply(resp, _trip(), [])
        assert out.named_interest is None
        assert expanded_with == []


class TestEnforcePins:
    """Live 2026-07-13 eval regression (RF-007 Barcelona: 3 correct pins, only
    1 honoured exactly-once with the tag): pin inclusion must be structural,
    not prompt-compliance-dependent."""

    def _item(self, title: str, tags: list[str] | None = None) -> ItineraryItem:
        return ItineraryItem(
            id=title.lower().replace(" ", "-"),
            time_start="10:00", time_end="12:00",
            title=title, description="…",
            location=ItineraryItemLocation(lat=0.0, lon=0.0),
            tags=tags or [],
        )

    def _day(self, number: int, items: list[ItineraryItem]) -> ItineraryDay:
        return ItineraryDay(day_number=number, date="2026-11-10",
                            theme="Day", items=items)

    def _trip_with_pins(self, names: list[str]) -> TripConfig:
        return _trip([PinnedPOI(name=n, lat=41.4, lon=2.17,
                                source_interest="Gaudi architecture")
                      for n in names])

    def test_untagged_match_gets_pinned_tag(self):
        days = [self._day(1, [self._item("Sagrada Família Basilica")])]
        out = _enforce_pins(days, self._trip_with_pins(["Sagrada Familia"]))
        assert out[0].items[0].tags == ["pinned"]

    def test_dropped_pin_is_injected_on_lightest_day(self):
        days = [
            self._day(1, [self._item("La Rambla"), self._item("Camp Nou")]),
            self._day(2, [self._item("Beach Walk")]),
        ]
        out = _enforce_pins(days, self._trip_with_pins(["Casa Batllo"]))
        injected = [i for d in out for i in d.items if "pinned" in i.tags]
        assert len(injected) == 1
        assert injected[0].title == "Casa Batllo"
        assert injected[0].location.lat == 41.4
        assert injected[0] in out[1].items  # lightest day

    def test_duplicate_tagged_matches_reduced_to_one(self):
        days = [self._day(1, [
            self._item("Park Guell", tags=["park", "pinned"]),
            self._item("Park Güell viewpoint", tags=["pinned"]),
        ])]
        out = _enforce_pins(days, self._trip_with_pins(["Park Guell"]))
        tagged = [i for i in out[0].items if "pinned" in i.tags]
        assert len(tagged) == 1
        assert tagged[0].title == "Park Guell"

    def test_no_pins_is_noop(self):
        days = [self._day(1, [self._item("La Rambla")])]
        out = _enforce_pins(days, _trip())
        assert out[0].items[0].tags == []


class TestMockItineraryHonoursPins:
    def test_pinned_place_appears_with_pinned_tag(self):
        trip = _trip([PinnedPOI(name="Warner Bros. Studio Tour London",
                                lat=51.69, lon=-0.42, source_interest="Harry Potter")])
        raw = _mock_itinerary(trip)
        titles = [i["title"] for d in raw["days"] for i in d["items"]]
        assert "Warner Bros. Studio Tour London" in titles
        pinned_items = [
            i for d in raw["days"] for i in d["items"] if "pinned" in i["tags"]
        ]
        assert len(pinned_items) == 1
        assert pinned_items[0]["location"]["lat"] == 51.69

    def test_no_pins_no_pinned_items(self):
        raw = _mock_itinerary(_trip())
        assert all("pinned" not in i["tags"] for d in raw["days"] for i in d["items"])
