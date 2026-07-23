"""Tests for the generic geocode disambiguation pipeline in
services/geocode.py — fully offline, mocking httpx per this repo's
convention for external-service tests."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.geocode import (
    GEOCODE_QUERY_OVERRIDES,
    _is_country_like,
    _needs_second_opinion,
    _pick_best_hit,
    geocode_city,
)


def _place_hit(name="Testville", country="Testland", cc="tt", ptype="city", importance=0.8, **address_extra):
    return {
        "display_name": f"{name}, {country}",
        "lat": "1.0",
        "lon": "2.0",
        "class": "place",
        "type": ptype,
        "importance": importance,
        "namedetails": {},
        "address": {"city": name, "country": country, "country_code": cc, **address_extra},
    }


def _boundary_hit(name="Regionia", country="Regionland", cc="rr", importance=0.5):
    return {
        "display_name": f"{name}, {country}",
        "lat": "10.0",
        "lon": "20.0",
        "class": "boundary",
        "type": "administrative",
        "importance": importance,
        "namedetails": {},
        "address": {"country": country, "country_code": cc},
    }


def test_pick_best_hit_prefers_place_over_boundary():
    hits = [_boundary_hit(), _place_hit()]
    assert _pick_best_hit(hits)["class"] == "place"


def test_pick_best_hit_falls_back_when_no_place_hit():
    hits = [_boundary_hit(), _boundary_hit(name="Other")]
    assert _pick_best_hit(hits) is hits[0]


def test_is_country_like_true_without_settlement_field():
    assert _is_country_like(_boundary_hit()) is True


def test_is_country_like_false_with_city_field():
    assert _is_country_like(_place_hit()) is False


def test_needs_second_opinion_low_importance():
    assert _needs_second_opinion(_place_hit(importance=0.1)) is True


def test_needs_second_opinion_small_settlement_type():
    assert _needs_second_opinion(_place_hit(ptype="village", importance=0.8)) is True


def test_needs_second_opinion_non_place_class():
    assert _needs_second_opinion(_boundary_hit(importance=0.9)) is True


def test_needs_second_opinion_false_for_confident_city():
    assert _needs_second_opinion(_place_hit(ptype="city", importance=0.8)) is False


def _mock_client(get_side_effect=None, post_return=None):
    client = AsyncMock()
    if get_side_effect is not None:
        client.get = AsyncMock(side_effect=get_side_effect)
    if post_return is not None:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = post_return
        client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _json_response(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


@pytest.mark.asyncio
async def test_geocode_city_confident_hit_skips_disambiguation():
    """A high-confidence city-class hit should return immediately without
    any Wikipedia/Overpass cross-check calls."""
    search_resp = _json_response([_place_hit(name="Bengaluru", country="India", cc="in", importance=0.8)])
    client = _mock_client(get_side_effect=[search_resp])

    with patch("services.geocode.httpx.AsyncClient", return_value=client), \
         patch("services.geocode.asyncio.sleep", new=AsyncMock()):
        result = await geocode_city("Bengaluru")

    assert result.display_name == "Bengaluru, India"
    assert result.is_country is False
    assert client.get.await_count == 1  # only the initial Nominatim search


@pytest.mark.asyncio
async def test_geocode_city_corrects_low_confidence_wrong_country_match():
    """Mirrors the real "Cappadocia" bug: Nominatim's top hit is an obscure,
    wrong-country village; Wikipedia's article for the same query points to
    the correct country, and the pipeline should prefer it."""
    wrong_country_hit = _place_hit(name="Cappadocia", country="Italy", cc="it", ptype="village", importance=0.15)
    search_resp = _json_response([wrong_country_hit])
    wiki_search_resp = _json_response({"query": {"search": [{"title": "Cappadocia"}]}})
    wiki_coords_resp = _json_response(
        {"query": {"pages": {"1": {"coordinates": [{"lat": 38.6, "lon": 34.8}]}}}}
    )
    reverse_resp = _json_response(_place_hit(name="Goreme", country="Turkey", cc="tr", importance=0.8))

    client = _mock_client(get_side_effect=[search_resp, wiki_search_resp, wiki_coords_resp, reverse_resp])

    with patch("services.geocode.httpx.AsyncClient", return_value=client), \
         patch("services.geocode.asyncio.sleep", new=AsyncMock()):
        result = await geocode_city("Cappadocia")

    assert result.country_code == "tr"
    assert "Turkey" in result.display_name


@pytest.mark.asyncio
async def test_geocode_city_country_hit_uses_hub_town_via_overpass():
    """Mirrors the real "Ladakh"/"Maldives" bug class: Nominatim resolves to
    a region/country-sized hit, so the pipeline should look up the largest
    settlement in its bounding box via Overpass and re-geocode using that."""
    region_hit = _boundary_hit(name="Regionia", country="Regionland", cc="rr")
    region_hit["boundingbox"] = ["10.0", "12.0", "20.0", "22.0"]
    search_resp = _json_response([region_hit])
    hub_requery_resp = _json_response(
        [_place_hit(name="Hubtown", country="Regionland", cc="rr", importance=0.6)]
    )

    client = _mock_client(
        get_side_effect=[search_resp, hub_requery_resp],
        post_return={"elements": [{"tags": {"name": "Hubtown", "place": "city", "population": "50000"}}]},
    )

    with patch("services.geocode.httpx.AsyncClient", return_value=client), \
         patch("services.geocode.asyncio.sleep", new=AsyncMock()):
        result = await geocode_city("Regionia")

    assert result.is_country is False
    assert "Hubtown" in result.display_name
    client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_geocode_city_skips_hub_town_lookup_for_oversized_bbox():
    """A country-sized bounding box (e.g. "Tokyo" resolving to the whole
    metropolis/prefecture) should not trigger an expensive Overpass query —
    it should fall back to the region-level hit instead."""
    region_hit = _boundary_hit(name="Tokyo", country="Japan", cc="jp")
    region_hit["boundingbox"] = ["20.0", "36.0", "135.0", "154.0"]
    search_resp = _json_response([region_hit])

    client = _mock_client(get_side_effect=[search_resp])

    with patch("services.geocode.httpx.AsyncClient", return_value=client), \
         patch("services.geocode.asyncio.sleep", new=AsyncMock()):
        result = await geocode_city("Tokyo")

    assert result.is_country is True
    client.post.assert_not_awaited() if hasattr(client.post, "assert_not_awaited") else None


@pytest.mark.asyncio
async def test_geocode_city_falls_back_to_wikipedia_when_nominatim_finds_nothing():
    search_resp = _json_response([])
    wiki_search_resp = _json_response({"query": {"search": [{"title": "Some Place"}]}})
    wiki_coords_resp = _json_response(
        {"query": {"pages": {"1": {"coordinates": [{"lat": 5.0, "lon": 6.0}]}}}}
    )
    reverse_resp = _json_response(_place_hit(name="Some Place", country="Elsewhere", cc="el", importance=0.7))

    client = _mock_client(get_side_effect=[search_resp, wiki_search_resp, wiki_coords_resp, reverse_resp])

    with patch("services.geocode.httpx.AsyncClient", return_value=client), \
         patch("services.geocode.asyncio.sleep", new=AsyncMock()):
        result = await geocode_city("Sum Plase")  # misspelled

    assert result.country_code == "el"


@pytest.mark.asyncio
async def test_geocode_city_raises_when_nothing_found_anywhere():
    search_resp = _json_response([])
    wiki_search_resp = _json_response({"query": {"search": []}})
    client = _mock_client(get_side_effect=[search_resp, wiki_search_resp])

    with patch("services.geocode.httpx.AsyncClient", return_value=client), \
         patch("services.geocode.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(ValueError):
            await geocode_city("Nowhereville12345xyz")


class TestGeocodeQueryOverrides:
    """Same-name-collision pins: a handful of destinations whose bare name
    resolves to the wrong same-named place, which no importance/country
    heuristic can disambiguate (Austin TX vs a Nevada ghost town — same
    country; La Paz/Valencia — real cities of comparable prominence to the
    intended one). The override must rewrite the Nominatim query string."""

    @pytest.mark.parametrize(
        "name, expected_query",
        [
            ("Austin", "Austin, Texas"),
            ("La Paz", "La Paz, Bolivia"),
            ("Valencia", "Valencia, Spain"),
        ],
    )
    @pytest.mark.asyncio
    async def test_override_rewrites_nominatim_query(self, name, expected_query):
        # A confident place hit so the pipeline returns after the first search
        # and we can inspect exactly what query string was sent to Nominatim.
        search_resp = _json_response([_place_hit(importance=0.8)])
        client = _mock_client(get_side_effect=[search_resp])

        with patch("services.geocode.httpx.AsyncClient", return_value=client), \
             patch("services.geocode.asyncio.sleep", new=AsyncMock()):
            await geocode_city(name)

        sent_query = client.get.await_args_list[0].kwargs["params"]["q"]
        assert sent_query == expected_query

    def test_overrides_are_lowercase_keyed(self):
        # geocode_city looks up city.strip().lower() — keys must be lowercase
        # or the override silently never fires.
        for key in GEOCODE_QUERY_OVERRIDES:
            assert key == key.lower()
