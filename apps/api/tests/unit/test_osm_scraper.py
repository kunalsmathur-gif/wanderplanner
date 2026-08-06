"""
Unit tests for scrapers/osm.py's landmark-prioritization fix.

Live-verified 2026-07-20: a single Overpass query unioning all POI tag
categories, combined with a flat result cap, let numerically-dominant
food/drink nodes crowd out landmarks entirely in dense urban cores (central
London within 5km returned 58/58 restaurant/cafe/bar nodes and zero
attractions/museums/monuments). fetch_osm_pois must over-fetch from Overpass
and prioritize non-food/drink categories before the final truncation.

Also live-verified 2026-07-20: a plain "food/drink last" stable sort isn't
enough on its own — any single *non*-food/drink category dense enough in a
given city reproduces the same starvation bug against the *other* landmark
categories (central Paris: 51/60 "train station" nodes; Tokyo: 40/60 "place
of worship" nodes, in both cases crowding out museums/attractions/theatres
almost entirely). `_prioritize_landmarks` round-robins across every category
present so no single one can dominate the cap.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scrapers.osm import (
    _OSM_RADIUS_OVERRIDES_M,
    _build_prominence_query,
    _display_name,
    _prioritize_landmarks,
    _prominence_score,
    _radius_override_for,
    fetch_osm_pois,
)


def _make_element(osm_id: int, name: str, tags: dict[str, str], lat: float = 51.5, lon: float = -0.1) -> dict:
    return {"id": osm_id, "type": "node", "lat": lat, "lon": lon, "tags": {"name": name, **tags}}


def _make_area(osm_id: int, name: str, tags: dict[str, str], lat: float = 51.5, lon: float = -0.1,
               kind: str = "way") -> dict:
    """A way/relation element as Overpass returns it under `out center` — no
    top-level lat/lon, a `center` object instead. Famous landmarks are mapped
    this way (Kiyomizu-dera and Kinkaku-ji are ways; Delhi's Jama Masjid is a
    relation), which is why the node-only query could never reach them."""
    return {"id": osm_id, "type": kind, "center": {"lat": lat, "lon": lon},
            "tags": {"name": name, **tags}}


def _make_response(elements: list[dict]) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"elements": elements}
    return response


def _mock_client(*responses) -> AsyncMock:
    """An httpx.AsyncClient mock returning `responses` in order — one per
    Overpass pass (prominence first, then broad)."""
    client = AsyncMock()
    client.post = AsyncMock(side_effect=list(responses))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


class TestDisplayName:
    """OSM's `name` tag is the *local-language* name. Live-audited
    2026-07-25: 59 of Kyoto's 60 ingested POIs were stored in Japanese script,
    so services/gems.py could never find them in English-language traveller
    comments and hidden gems returned an empty list for the city despite 237
    ingested comments. A live Overpass probe found `name:en` on 43 of 107
    named Kyoto nodes."""

    def test_prefers_name_en(self):
        assert _display_name({"name": "興正寺", "name:en": "Koshoji Temple"}) == "Koshoji Temple"

    def test_falls_back_to_int_name(self):
        assert _display_name({"name": "白峯神宮", "int_name": "Shiramine Jingu"}) == "Shiramine Jingu"

    def test_extracts_latin_parenthetical_from_local_script_name(self):
        """Some nodes carry no name:en but bracket the Latin form inline."""
        assert _display_name({"name": "新熊野神社 (Imakumano Shrine)"}) == "Imakumano Shrine"

    def test_parenthetical_left_alone_when_name_is_already_latin(self):
        """Brackets on a Latin name are a disambiguator, not a translation —
        promoting them would rename the POI to its country."""
        assert _display_name({"name": "Victoria (Seychelles)"}) == "Victoria (Seychelles)"

    def test_latin_local_name_passes_through_unchanged(self):
        assert _display_name({"name": "Kadıköy"}) == "Kadıköy"

    def test_untranslated_local_script_name_is_kept(self):
        """Better a name we can't match than no POI at all — it still carries
        real coordinates for the itinerary."""
        assert _display_name({"name": "正覺寺"}) == "正覺寺"

    def test_unnamed_node_yields_empty(self):
        assert _display_name({"tourism": "attraction"}) == ""


class TestPrioritizeLandmarks:
    def test_landmarks_survive_ahead_of_food_drink(self):
        pois = [
            {"poi_type": "restaurant", "name": "R1"},
            {"poi_type": "cafe", "name": "C1"},
            {"poi_type": "attraction", "name": "Big Ben"},
            {"poi_type": "bar", "name": "B1"},
            {"poi_type": "museum", "name": "British Museum"},
        ]
        ordered = _prioritize_landmarks(pois)
        # Both landmarks must appear before any food/drink entry.
        landmark_names = {"Big Ben", "British Museum"}
        first_two = {p["name"] for p in ordered[:2]}
        assert first_two == landmark_names

    def test_stable_within_each_tier(self):
        # Relative order preserved among same-tier entries (stable sort).
        pois = [
            {"poi_type": "restaurant", "name": "R1"},
            {"poi_type": "attraction", "name": "A1"},
            {"poi_type": "restaurant", "name": "R2"},
            {"poi_type": "attraction", "name": "A2"},
        ]
        ordered = _prioritize_landmarks(pois)
        assert [p["name"] for p in ordered] == ["A1", "A2", "R1", "R2"]

    def test_food_drink_still_included_when_no_landmarks_present(self):
        pois = [{"poi_type": "restaurant", "name": "R1"}, {"poi_type": "cafe", "name": "C1"}]
        ordered = _prioritize_landmarks(pois)
        assert len(ordered) == 2

    def test_no_single_category_dominates_after_truncation(self):
        # Regression test for the Paris/Tokyo finding: one numerous category
        # (here "train station") must not crowd out other landmark
        # categories once the result is truncated to a small cap.
        pois = (
            [{"poi_type": "train station", "name": f"Station {i}"} for i in range(50)]
            + [{"poi_type": "museum", "name": f"Museum {i}"} for i in range(3)]
            + [{"poi_type": "attraction", "name": f"Attraction {i}"} for i in range(3)]
            + [{"poi_type": "theatre", "name": f"Theatre {i}"} for i in range(3)]
        )
        ordered = _prioritize_landmarks(pois)
        top_12 = ordered[:12]
        categories_in_top_12 = {p["poi_type"] for p in top_12}
        # All four categories should be represented well within the first 12
        # slots — round-robin guarantees this regardless of how many
        # "train station" nodes exist.
        assert categories_in_top_12 == {"train station", "museum", "attraction", "theatre"}


class TestProminenceScore:
    """Live-measured 2026-07-25: the ingested pool held 21 obscure Kyoto
    temples and 20 small museums but not Kiyomizu-dera or Kinkaku-ji, because
    nothing ranked by prominence and the slots went to whatever Overpass
    returned first. `wikidata`/`wikipedia`/`heritage` are the free signal that
    separates the two — famous sites carry them, neighbourhood shrines
    don't."""

    def test_unremarkable_poi_scores_zero(self):
        assert _prominence_score({"name": "Corner Shrine", "amenity": "place_of_worship"}) == 0

    def test_wikidata_and_wikipedia_outrank_a_bare_website(self):
        famous = _prominence_score({"wikidata": "Q1030", "wikipedia": "en:Kiyomizu-dera"})
        has_site = _prominence_score({"website": "https://example.com"})
        assert famous > has_site > 0

    def test_world_heritage_listing_outranks_plain_heritage(self):
        world = _prominence_score({"heritage": "1"})
        national = _prominence_score({"heritage": "2"})
        assert world > national > 0

    def test_english_name_is_a_weak_signal(self):
        assert _prominence_score({"name:en": "Golden Pavilion"}) > 0
        assert _prominence_score({"int_name": "Golden Pavilion"}) > 0

    def test_signals_accumulate(self):
        both = _prominence_score({"wikidata": "Q1", "heritage": "1", "website": "x", "name:en": "y"})
        one = _prominence_score({"wikidata": "Q1"})
        assert both > one


class TestProminenceQuery:
    """The prominence pass has to ask for ways and relations, must not carry a
    result cap, and must leave out the categories it isn't for."""

    def test_asks_for_nodes_ways_and_relations(self):
        query = _build_prominence_query(35.0, 135.0, 15000)
        assert "nwr[" in query
        # A node-only query is exactly the bug being fixed: Kiyomizu-dera,
        # Kinkaku-ji and Ginkaku-ji are all `way` elements.
        assert 'node["' not in query

    def test_filters_to_prominent_elements(self):
        assert '["wikidata"]' in _build_prominence_query(35.0, 135.0, 15000)

    def test_has_no_result_cap(self):
        # Overpass's `out <limit>` truncates in element-type order, nodes
        # first — so any cap here would silently drop every way and relation,
        # which is the whole point of the pass. Live-verified: an `nwr` query
        # capped at 3000 for Kyoto came back 3000/3000 nodes.
        assert _build_prominence_query(35.0, 135.0, 15000).rstrip().endswith("out center;")

    def test_excludes_transport_and_food_drink(self):
        query = _build_prominence_query(35.0, 135.0, 15000)
        for excluded in ('"railway"="station"', '"aeroway"="aerodrome"',
                         '"amenity"="restaurant"', '"amenity"="cafe"', '"amenity"="bar"'):
            assert excluded not in query
        # ...but still covers what a traveller plans a day around.
        assert '"tourism"="attraction"' in query
        assert '"historic"="monument"' in query

    def test_uses_the_radius_it_is_given(self):
        assert "around:15000," in _build_prominence_query(35.0, 135.0, 15000)


class TestProminenceRanking:
    def test_prominent_poi_wins_its_category_slot(self):
        pois = [
            {"poi_type": "place of worship", "name": "Corner Shrine", "prominence": 0},
            {"poi_type": "place of worship", "name": "Kiyomizu-dera", "prominence": 7},
            {"poi_type": "place of worship", "name": "Another Shrine", "prominence": 0},
        ]
        ordered = _prioritize_landmarks(pois)
        assert ordered[0]["name"] == "Kiyomizu-dera"

    def test_prominence_does_not_let_one_category_dominate(self):
        # The anti-domination guarantee has to survive prominence ranking.
        # Delhi is monument-dense: dozens of monuments are *genuinely* the
        # most prominent things in the city, so they rightly outrank a
        # nondescript museum — but they must not take every slot. The cap
        # bounds them and defers the rest behind the other categories.
        pois = (
            [{"poi_type": "historic monument", "name": f"Monument {i}", "prominence": 9}
             for i in range(40)]
            + [{"poi_type": "museum", "name": "Museum", "prominence": 1}]
            + [{"poi_type": "park", "name": "Park", "prominence": 0}]
        )
        ordered = _prioritize_landmarks(pois)
        names = [p["name"] for p in ordered]
        cap = round(60 * 0.25)  # settings.osm_poi_max_results * _MAX_CATEGORY_SHARE_IN_POOL

        # The most prominent category leads, but only up to the cap.
        assert all(p["poi_type"] == "historic monument" for p in ordered[:cap])
        # Then the other categories, ahead of the deferred monument overflow.
        assert names[cap:cap + 2] == ["Museum", "Park"]
        # Nothing is thrown away — a thin destination must not lose POIs.
        assert len(ordered) == 42

    def test_overflow_is_deferred_not_discarded(self):
        pois = [{"poi_type": "train station", "name": f"S{i}", "prominence": 0} for i in range(50)]
        assert len(_prioritize_landmarks(pois)) == 50

    def test_missing_prominence_key_is_treated_as_zero(self):
        # _prioritize_landmarks is also called on POIs that predate the
        # prominence field (and by tests that don't set it) — it must not
        # raise, and must fall back to arrival order.
        pois = [
            {"poi_type": "museum", "name": "M1"},
            {"poi_type": "museum", "name": "M2"},
        ]
        assert [p["name"] for p in _prioritize_landmarks(pois)] == ["M1", "M2"]

    def test_ties_keep_arrival_order(self):
        pois = [
            {"poi_type": "museum", "name": "M1", "prominence": 3},
            {"poi_type": "museum", "name": "M2", "prominence": 3},
            {"poi_type": "museum", "name": "M3", "prominence": 3},
        ]
        assert [p["name"] for p in _prioritize_landmarks(pois)] == ["M1", "M2", "M3"]


class TestTwoPassFetch:
    @pytest.mark.asyncio
    async def test_way_and_relation_landmarks_are_ingested(self):
        # The regression this whole change exists for: before it, a node-only
        # query meant these were not out-ranked, they were unreachable.
        prominence = [
            _make_area(1, "Kiyomizu-dera", {"tourism": "attraction", "wikidata": "Q1030"},
                       lat=34.99, lon=135.78),
            _make_area(2, "Jama Masjid", {"amenity": "place_of_worship", "wikidata": "Q207286"},
                       kind="relation", lat=28.65, lon=77.23),
        ]
        broad = [_make_element(3, "Some Cafe", {"amenity": "cafe"})]

        with patch("scrapers.osm.httpx.AsyncClient",
                   return_value=_mock_client(_make_response(prominence), _make_response(broad))):
            pois = await fetch_osm_pois("Kyoto", lat=35.0116, lon=135.7681)

        by_name = {p["name"]: p for p in pois}
        assert "Kiyomizu-dera" in by_name
        assert "Jama Masjid" in by_name
        # `center` is what ways/relations carry instead of lat/lon.
        assert by_name["Kiyomizu-dera"]["lat"] == 34.99
        # The OSM link has to point at the right element type or it 404s.
        assert by_name["Jama Masjid"]["source_url"].endswith("/relation/2")
        assert by_name["Kiyomizu-dera"]["source_url"].endswith("/way/1")

    @pytest.mark.asyncio
    async def test_prominent_duplicate_beats_the_plain_node(self):
        # A landmark is often mapped twice — an area carrying the real tags
        # and a bare node. Dedup is by name, so the prominence pass has to be
        # merged first or the richer element loses to the emptier one.
        prominence = [_make_area(1, "Kinkaku-ji", {"tourism": "attraction", "wikidata": "Q200016",
                                                   "heritage": "1"})]
        broad = [_make_element(2, "Kinkaku-ji", {"tourism": "attraction"})]

        with patch("scrapers.osm.httpx.AsyncClient",
                   return_value=_mock_client(_make_response(prominence), _make_response(broad))):
            pois = await fetch_osm_pois("Kyoto", lat=35.0116, lon=135.7681)

        kept = [p for p in pois if p["name"] == "Kinkaku-ji"]
        assert len(kept) == 1
        assert kept[0]["prominence"] > 0
        assert kept[0]["source_url"].endswith("/way/1")

    @pytest.mark.asyncio
    async def test_broad_pass_still_works_when_prominence_pass_fails(self):
        # Overpass is genuinely flaky and the prominence query is the heavier
        # of the two. Losing it must degrade to the old behaviour, not to an
        # empty destination.
        broad = [_make_element(1, "Tower Bridge", {"tourism": "attraction"})]
        client = _mock_client(
            *([Exception("504 Gateway Timeout")] * 4),  # prominence pass, exhausted
            _make_response(broad),
        )

        with patch("scrapers.osm.httpx.AsyncClient", return_value=client), \
             patch("scrapers.osm.asyncio.sleep", new=AsyncMock()):
            pois = await fetch_osm_pois("London", lat=51.5074, lon=-0.1278)

        assert [p["name"] for p in pois] == ["Tower Bridge"]

    @pytest.mark.asyncio
    async def test_prominence_pass_alone_is_enough_when_broad_pass_fails(self):
        prominence = [_make_area(1, "Kiyomizu-dera", {"tourism": "attraction", "wikidata": "Q1030"})]
        client = _mock_client(
            _make_response(prominence),
            *([Exception("504 Gateway Timeout")] * 5),  # broad pass, exhausted
        )

        with patch("scrapers.osm.httpx.AsyncClient", return_value=client), \
             patch("scrapers.osm.asyncio.sleep", new=AsyncMock()):
            pois = await fetch_osm_pois("Kyoto", lat=35.0116, lon=135.7681)

        assert [p["name"] for p in pois] == ["Kiyomizu-dera"]

    @pytest.mark.asyncio
    async def test_prominence_pass_widens_with_the_callers_radius(self):
        # ingest_osm_pois retries thin destinations at the expanded radius;
        # the prominent set has to widen with it rather than stay at 15km.
        client = _mock_client(_make_response([]), _make_response([]))
        with patch("scrapers.osm.httpx.AsyncClient", return_value=client), \
             patch("scrapers.osm.settings.osm_prominence_radius_m", 15000):
            await fetch_osm_pois("Nowhere", lat=0.0, lon=0.0, radius_m=40000)

        prominence_query = client.post.await_args_list[0].kwargs["data"]["data"]
        assert "around:40000," in prominence_query

    @pytest.mark.asyncio
    async def test_prominence_pass_uses_the_wider_radius_by_default(self):
        client = _mock_client(_make_response([]), _make_response([]))
        with patch("scrapers.osm.httpx.AsyncClient", return_value=client), \
             patch("scrapers.osm.settings.osm_poi_radius_m", 5000), \
             patch("scrapers.osm.settings.osm_prominence_radius_m", 15000):
            await fetch_osm_pois("Delhi", lat=28.6139, lon=77.2090)

        prominence_query = client.post.await_args_list[0].kwargs["data"]["data"]
        broad_query = client.post.await_args_list[1].kwargs["data"]["data"]
        # Live-probed: Delhi at 5km misses Red Fort, Qutub Minar, Lotus Temple
        # and Chandni Chowk; at 15km it finds all four.
        assert "around:15000," in prominence_query
        assert "around:5000," in broad_query


class TestFetchOsmPoisTruncation:
    @pytest.mark.asyncio
    async def test_final_cap_keeps_landmarks_over_food_drink(self):
        # 3 food/drink nodes + 1 landmark node, cap of 2 — the landmark must
        # survive even though it appears last in Overpass's raw ordering.
        elements = [
            _make_element(1, "R1", {"amenity": "restaurant"}),
            _make_element(2, "C1", {"amenity": "cafe"}),
            _make_element(3, "B1", {"amenity": "bar"}),
            _make_element(4, "Tower Bridge", {"tourism": "attraction"}),
        ]
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"elements": elements}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.osm.httpx.AsyncClient", return_value=mock_client), \
             patch("scrapers.osm.settings.osm_poi_max_results", 2):
            pois = await fetch_osm_pois("London", lat=51.5074, lon=-0.1278)

        assert len(pois) == 2
        assert "Tower Bridge" in {p["name"] for p in pois}

    @pytest.mark.asyncio
    async def test_ingested_name_is_english_with_local_name_retained(self):
        elements = [
            _make_element(1, "清水寺", {"tourism": "attraction", "name:en": "Kiyomizu-dera"}),
            _make_element(2, "Nishiki Market", {"shop": "marketplace"}),
        ]
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"elements": elements}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.osm.httpx.AsyncClient", return_value=mock_client):
            pois = await fetch_osm_pois("Kyoto", lat=35.0116, lon=135.7681)

        by_name = {p["name"]: p for p in pois}
        assert "Kiyomizu-dera" in by_name
        assert by_name["Kiyomizu-dera"]["name_local"] == "清水寺"
        # Nothing to retain when the local name is the one we're already using.
        assert by_name["Nishiki Market"]["name_local"] == ""

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_network_failure(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.osm.httpx.AsyncClient", return_value=mock_client), \
             patch("scrapers.osm.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            pois = await fetch_osm_pois("Nowhere", lat=0.0, lon=0.0)

        assert pois == []
        # Both passes exhaust their own budget: 4 for the supplementary
        # prominence pass, then 5 for the load-bearing broad pass.
        assert mock_client.post.await_count == 4 + 5
        assert mock_sleep.await_count == 3 + 4

    @pytest.mark.asyncio
    async def test_retries_transient_failure_then_succeeds(self):
        # Overpass frequently 504s under load and succeeds seconds later —
        # found live 2026-07-20. A transient failure on the first attempt
        # must not be treated the same as a permanent one.
        prominence_response = _make_response([])
        broad_response = _make_response([_make_element(1, "Tower Bridge", {"tourism": "attraction"})])
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[
            Exception("504 Gateway Timeout"), prominence_response,   # prominence pass
            Exception("504 Gateway Timeout"), broad_response,        # broad pass
        ])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.osm.httpx.AsyncClient", return_value=mock_client), \
             patch("scrapers.osm.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            pois = await fetch_osm_pois("London", lat=51.5074, lon=-0.1278)

        assert len(pois) == 1
        assert pois[0]["name"] == "Tower Bridge"
        assert mock_client.post.await_count == 4
        assert mock_sleep.await_count == 2

    @pytest.mark.asyncio
    async def test_rotates_across_mirrors_on_repeated_failure(self):
        # 2026-07-23: repeated Overpass failures must not all retry against
        # the same instance — spread across the configured mirrors so one
        # rate-limited/overloaded instance doesn't eat the whole retry budget.
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("504 Gateway Timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.osm.httpx.AsyncClient", return_value=mock_client), \
             patch("scrapers.osm.asyncio.sleep", new=AsyncMock()), \
             patch(
                "scrapers.osm.settings.osm_overpass_fallback_mirrors",
                ["https://mirror-a", "https://mirror-b"],
            ):
            await fetch_osm_pois("Nowhere", lat=0.0, lon=0.0)

        called_urls = [call.args[0] for call in mock_client.post.await_args_list]
        assert called_urls == [
            # prominence pass — 4 attempts
            "https://overpass-api.de/api/interpreter",
            "https://mirror-a",
            "https://mirror-b",
            "https://overpass-api.de/api/interpreter",
            # broad pass — 5 attempts, restarting the rotation
            "https://overpass-api.de/api/interpreter",
            "https://mirror-a",
            "https://mirror-b",
            "https://overpass-api.de/api/interpreter",
            "https://mirror-a",
        ]


class TestIngestOsmPoisOrphanCleanup:
    """ingest_osm_pois() must delete-then-upsert per destination — found live
    2026-07-20 that re-ingesting London with the round-robin fix left the old
    all-food/drink points in place (58 -> 112, not 58 -> 60), doubling the
    collection and diluting services/poi_pinning.py's fuzzy-name matching."""

    @pytest.mark.asyncio
    async def test_deletes_stale_points_before_upserting_new_ones(self):
        from scrapers.osm import ingest_osm_pois

        fake_pois = [
            {
                "destination": "London", "name": "Tower Bridge", "poi_type": "attraction",
                "lat": 51.5, "lon": -0.1, "tags": {}, "text": "Tower Bridge is an attraction in London.",
                "source": "osm", "source_url": "https://www.openstreetmap.org/node/1",
            },
        ]
        mock_qdrant = MagicMock()

        with patch("scrapers.osm._fetch_osm_pois_with_meta", new=AsyncMock(return_value=(fake_pois, True, False))), \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384]), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=0), \
             patch("scrapers.osm.delete_stale_destination_points", return_value=2) as mock_delete:
            count = await ingest_osm_pois("London")

        assert count == 1
        mock_delete.assert_called_once()
        args, _ = mock_delete.call_args
        assert args[0] is mock_qdrant
        assert args[2] == "London"
        mock_qdrant.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_cleanup_call_when_fetch_returns_nothing(self):
        # A failed/empty fetch must not wipe out a destination's existing
        # real data — only clean up when there's something new to replace it.
        from scrapers.osm import ingest_osm_pois

        with patch("scrapers.osm._fetch_osm_pois_with_meta", new=AsyncMock(return_value=([], True, False))), \
             patch("scrapers.osm.delete_stale_destination_points") as mock_delete:
            count = await ingest_osm_pois("Nowhere")

        assert count == 0
        mock_delete.assert_not_called()


class TestRadiusExpansionForThinOrDominatedResults:
    """A thin (<20 POIs) or single-category-dominated (>50% one poi_type)
    default-radius result must trigger a second fetch at the wider
    `osm_poi_radius_expanded_m` radius before ingest_osm_pois accepts it —
    small towns/"hidden gem" destinations often have their few landmark/
    nature POIs spread wider than 5km. Live-confirmed 2026-07-23 for Coorg/
    Jaisalmer (restaurant-dominated) and Spiti/Nainital (thin OSM)."""

    def _poi(self, name: str, poi_type: str) -> dict:
        return {
            "destination": "X", "name": name, "poi_type": poi_type,
            "lat": 0.0, "lon": 0.0, "tags": {}, "text": f"{name} is a {poi_type} in X.",
            "source": "osm", "source_url": "https://www.openstreetmap.org/node/1",
        }

    @pytest.mark.asyncio
    async def test_expands_radius_when_thin(self):
        from scrapers.osm import ingest_osm_pois

        thin = [self._poi(f"Landmark {i}", "attraction") for i in range(5)]
        wide = [self._poi(f"Landmark {i}", "attraction") for i in range(25)]
        mock_qdrant = MagicMock()

        with patch("scrapers.osm._fetch_osm_pois_with_meta", new=AsyncMock(side_effect=[(thin, True, False), (wide, True, False)])) as mock_fetch, \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384] * 25), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=0), \
             patch("scrapers.osm.delete_stale_destination_points", return_value=0):
            count = await ingest_osm_pois("Spiti")

        assert count == 25
        assert mock_fetch.await_count == 2
        _, kwargs = mock_fetch.await_args
        assert kwargs["radius_m"] == 15000

    @pytest.mark.asyncio
    async def test_expands_radius_when_category_dominated(self):
        from scrapers.osm import ingest_osm_pois

        dominated = [self._poi(f"R{i}", "restaurant") for i in range(19)] + [self._poi("Fort", "attraction")]
        balanced = [self._poi(f"R{i}", "restaurant") for i in range(10)] + [
            self._poi(f"Landmark {i}", "attraction") for i in range(15)
        ]
        mock_qdrant = MagicMock()

        with patch("scrapers.osm._fetch_osm_pois_with_meta", new=AsyncMock(side_effect=[(dominated, True, False), (balanced, True, False)])) as mock_fetch, \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384] * 25), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=0), \
             patch("scrapers.osm.delete_stale_destination_points", return_value=0):
            count = await ingest_osm_pois("Jaisalmer")

        assert count == 25
        assert mock_fetch.await_count == 2

    @pytest.mark.asyncio
    async def test_keeps_default_radius_result_when_healthy(self):
        from scrapers.osm import ingest_osm_pois

        healthy = [self._poi(f"Landmark {i}", "attraction") for i in range(15)] + [
            self._poi(f"R{i}", "restaurant") for i in range(15)
        ]
        mock_qdrant = MagicMock()

        with patch("scrapers.osm._fetch_osm_pois_with_meta", new=AsyncMock(return_value=(healthy, True, False))) as mock_fetch, \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384] * 30), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.delete_stale_destination_points", return_value=0):
            count = await ingest_osm_pois("London")

        assert count == 30
        mock_fetch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_original_when_expanded_fetch_still_bad(self):
        # Overpass returns nothing usable at the wider radius either (e.g.
        # transient failure exhausts retries) — keep the original thin
        # result rather than discarding real data for nothing.
        from scrapers.osm import ingest_osm_pois

        thin = [self._poi(f"Landmark {i}", "attraction") for i in range(5)]
        mock_qdrant = MagicMock()

        with patch("scrapers.osm._fetch_osm_pois_with_meta", new=AsyncMock(side_effect=[(thin, True, False), ([], True, False)])) as mock_fetch, \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384] * 5), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=0), \
             patch("scrapers.osm.delete_stale_destination_points", return_value=0):
            count = await ingest_osm_pois("Nowhereville")

        assert count == 5
        assert mock_fetch.await_count == 2


class TestDataLossGuardForThinResults:
    """A thin-but-non-empty new fetch must not clobber a substantially
    larger existing dataset — Overpass can silently return truncated
    results without raising, so emptiness alone isn't a safe guard."""

    def _poi(self, name: str, poi_type: str) -> dict:
        return {
            "destination": "X", "name": name, "poi_type": poi_type,
            "lat": 0.0, "lon": 0.0, "tags": {}, "text": f"{name} is a {poi_type} in X.",
            "source": "osm", "source_url": "https://www.openstreetmap.org/node/1",
        }

    @pytest.mark.asyncio
    async def test_skips_overwrite_when_existing_data_is_more_substantial(self):
        from scrapers.osm import ingest_osm_pois

        thin = [self._poi("Only POI", "attraction")]
        mock_qdrant = MagicMock()

        with patch("scrapers.osm._fetch_osm_pois_with_meta", new=AsyncMock(side_effect=[(thin, True, False), (thin, True, False)])), \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384]), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=60), \
             patch("scrapers.osm.delete_stale_destination_points") as mock_delete:
            count = await ingest_osm_pois("Las Vegas")

        assert count == 60
        mock_delete.assert_not_called()
        mock_qdrant.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_overwrites_when_new_thin_result_is_not_worse(self):
        from scrapers.osm import ingest_osm_pois

        thin = [self._poi("Only POI", "attraction")]
        mock_qdrant = MagicMock()

        with patch("scrapers.osm._fetch_osm_pois_with_meta", new=AsyncMock(side_effect=[(thin, True, False), (thin, True, False)])), \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384]), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=0), \
             patch("scrapers.osm.delete_stale_destination_points", return_value=0) as mock_delete:
            count = await ingest_osm_pois("Brand New Place")

        assert count == 1
        mock_delete.assert_called_once()


class TestHardRefusalRotatesWithoutBackoff:
    """Live-measured 2026-07-25 during the prominence re-ingestion:
    `overpass.openstreetmap.fr` answered 403 to 5 of 5 requests while the other
    two mirrors were still serving. Backing off before moving on wasted both a
    retry slot and an exponential sleep on a mirror that was never going to
    answer."""

    def _http_error(self, status: int) -> Exception:
        response = MagicMock()
        response.status_code = status
        error = Exception(f"HTTP {status}")
        error.response = response  # type: ignore[attr-defined]  # mimics httpx.HTTPStatusError
        return error

    @pytest.mark.asyncio
    async def test_403_rotates_immediately_and_succeeds_on_next_mirror(self):
        broad = [_make_element(1, "Tower Bridge", {"tourism": "attraction"})]
        client = _mock_client(
            self._http_error(403), _make_response([]),      # prominence: refused, then ok
            self._http_error(403), _make_response(broad),   # broad: refused, then ok
        )
        with patch("scrapers.osm.httpx.AsyncClient", return_value=client), \
             patch("scrapers.osm.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            pois = await fetch_osm_pois("London", lat=51.5074, lon=-0.1278)

        assert [p["name"] for p in pois] == ["Tower Bridge"]
        # The whole point: no waiting before rotating off a refusing mirror.
        mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_429_still_backs_off(self):
        # Rate limiting *is* congestion — that one must keep its backoff, or
        # we'd hammer a mirror that just asked us to slow down.
        client = _mock_client(
            self._http_error(429), _make_response([]),
            self._http_error(429), _make_response([]),
        )
        with patch("scrapers.osm.httpx.AsyncClient", return_value=client), \
             patch("scrapers.osm.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await fetch_osm_pois("London", lat=51.5074, lon=-0.1278)

        assert mock_sleep.await_count == 2

    @pytest.mark.asyncio
    async def test_server_error_still_backs_off(self):
        client = _mock_client(
            self._http_error(504), _make_response([]),
            self._http_error(504), _make_response([]),
        )
        with patch("scrapers.osm.httpx.AsyncClient", return_value=client), \
             patch("scrapers.osm.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await fetch_osm_pois("London", lat=51.5074, lon=-0.1278)

        assert mock_sleep.await_count == 2


class TestIngestGuardsAgainstProminencePassFailure:
    """A broad-pass-only result passes every other health check here — full
    count, well-spread categories — while containing none of the landmarks the
    destination is known for. Live-hit on this change's first run: Delhi's
    prominence query 403'd on all three mirrors and the fallback pool held
    none of Red Fort, Humayun's Tomb, Qutub Minar, India Gate, Lotus Temple,
    Jama Masjid or Lodhi Gardens, yet looked entirely healthy."""

    def _healthy_pool(self) -> list[dict]:
        return [
            {
                "destination": "Delhi", "name": f"POI {i}",
                "poi_type": ["attraction", "museum", "park", "theatre"][i % 4],
                "lat": 0.0, "lon": 0.0, "prominence": 0, "tags": {},
                "text": "x", "source": "osm",
                "source_url": "https://www.openstreetmap.org/node/1",
            }
            for i in range(60)
        ]

    @pytest.mark.asyncio
    async def test_keeps_existing_data_when_prominence_pass_failed(self):
        from scrapers.osm import ingest_osm_pois

        mock_qdrant = MagicMock()
        with patch("scrapers.osm._fetch_osm_pois_with_meta",
                   new=AsyncMock(return_value=(self._healthy_pool(), False, False))), \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384]), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=60), \
             patch("scrapers.osm.delete_stale_destination_points") as mock_delete:
            count = await ingest_osm_pois("Delhi")

        assert count == 60
        mock_delete.assert_not_called()
        mock_qdrant.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_still_ingests_a_brand_new_destination(self):
        # Degraded data beats no data when there is nothing to protect — this
        # must not turn a flaky prominence query into a permanently empty
        # destination for a first-time cold-start request.
        from scrapers.osm import ingest_osm_pois

        mock_qdrant = MagicMock()
        with patch("scrapers.osm._fetch_osm_pois_with_meta",
                   new=AsyncMock(return_value=(self._healthy_pool(), False, False))), \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384] * 60), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=0), \
             patch("scrapers.osm.delete_stale_destination_points", return_value=0):
            count = await ingest_osm_pois("Somewhere New")

        assert count == 60
        mock_qdrant.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_prominence_result_is_not_treated_as_failure(self):
        # A rural destination can legitimately have no wikidata-tagged POI at
        # all. That must still ingest — otherwise thinly-mapped destinations
        # could never be refreshed.
        from scrapers.osm import ingest_osm_pois

        mock_qdrant = MagicMock()
        with patch("scrapers.osm._fetch_osm_pois_with_meta",
                   new=AsyncMock(return_value=(self._healthy_pool(), True, False))), \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384] * 60), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=60), \
             patch("scrapers.osm.delete_stale_destination_points", return_value=0):
            count = await ingest_osm_pois("Sleepy Village")

        assert count == 60
        mock_qdrant.upsert.assert_called_once()


class TestRegionScaleRadiusOverrides:
    """Region-scale destinations (islands, multi-town areas) need a wider
    Overpass radius than the city-shaped 5km default — see
    `_OSM_RADIUS_OVERRIDES_M`'s comment for the Bali measurements."""

    def test_bali_is_overridden(self):
        assert _radius_override_for("Bali") == 30000

    def test_lookup_is_case_and_whitespace_insensitive(self):
        # ingest_osm_pois passes the raw destination string through.
        assert _radius_override_for("  bali ") == 30000
        assert _radius_override_for("BALI") == 30000

    def test_ordinary_city_has_no_override(self):
        assert _radius_override_for("Jaipur") is None

    def test_override_exceeds_the_thin_retry_radius(self):
        """The thin/dominated retry widens to `osm_poi_radius_expanded_m`. Any
        override at or below it would be silently undone by that retry, which
        is the regression the max() guard in ingest_osm_pois prevents."""
        from core.config import settings
        for name, radius in _OSM_RADIUS_OVERRIDES_M.items():
            assert radius > settings.osm_poi_radius_expanded_m, name


class TestIngestGuardsAgainstDegradedGeocode:
    """🔴 The geocode itself can be wrong, and the fetch looks perfect anyway.

    `geocode_city` corrects a region name to its hub town via an Overpass
    lookup — so when Overpass throttles, that correction fails and the raw
    region centroid is used instead. The resulting fetch has the right count,
    well-spread categories and a healthy prominence pass, and is centred tens
    of km from what the destination name means. Bali's 25 stored POIs sat 48km
    from Denpasar, in the wrong half of the island, written by exactly this
    path (2026-08-05).

    Same contract as the prominence guard: protect an overwrite, never block a
    cold start.
    """

    def _healthy_pool(self) -> list[dict]:
        return [
            {"destination": "Someregion", "name": f"POI {i}",
             "poi_type": ["attraction", "museum", "park", "beach"][i % 4],
             "lat": 1.0, "lon": 1.0, "text": f"POI {i}"}
            for i in range(60)
        ]

    @pytest.mark.asyncio
    async def test_keeps_existing_data_when_the_geocode_is_unverified(self):
        from scrapers.osm import ingest_osm_pois

        mock_qdrant = MagicMock()
        with patch("scrapers.osm._fetch_osm_pois_with_meta",
                   new=AsyncMock(return_value=(self._healthy_pool(), True, True))), \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384]), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=60), \
             patch("scrapers.osm.delete_stale_destination_points") as mock_delete:
            count = await ingest_osm_pois("Someregion")

        assert count == 60
        mock_delete.assert_not_called()
        mock_qdrant.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_still_ingests_a_brand_new_destination(self):
        """Wrong-place data beats no data when there is nothing to protect —
        and the destination stays flagged for a later pass."""
        from scrapers.osm import ingest_osm_pois

        mock_qdrant = MagicMock()
        with patch("scrapers.osm._fetch_osm_pois_with_meta",
                   new=AsyncMock(return_value=(self._healthy_pool(), True, True))), \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384] * 60), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=0), \
             patch("scrapers.osm.delete_stale_destination_points", return_value=0):
            count = await ingest_osm_pois("Somewhere New")

        assert count == 60
        mock_qdrant.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_a_verified_geocode_ingests_normally(self):
        """The control: identical fetch, geocode not degraded."""
        from scrapers.osm import ingest_osm_pois

        mock_qdrant = MagicMock()
        with patch("scrapers.osm._fetch_osm_pois_with_meta",
                   new=AsyncMock(return_value=(self._healthy_pool(), True, False))), \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384] * 60), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=60), \
             patch("scrapers.osm.delete_stale_destination_points", return_value=0):
            count = await ingest_osm_pois("Someregion")

        assert count == 60
        mock_qdrant.upsert.assert_called_once()


class TestMultiAreaSampling:
    """A single centre plus a radius assumes a destination is small and
    disc-shaped. Measured on Goa (a ~105km state) 2026-08-05: at the 5km
    default the pool held 5 North Goa POIs and ZERO from South Goa, with
    Agonda (52.6km) and Palolem (57.4km) structurally unreachable. Widening to
    one 60km circle measured WORSE — POIs 83.7km out, past the state border,
    and 15/60 slots refilled with train stations. Hence several centres."""

    def test_span_recognises_a_large_destination(self):
        from scrapers.osm import _bbox_span_km
        goa = (14.75, 15.80, 73.67, 74.33)
        assert _bbox_span_km(goa) > 100

    def test_span_recognises_a_small_one(self):
        from scrapers.osm import _bbox_span_km
        panaji = (15.47, 15.51, 73.80, 73.85)
        assert _bbox_span_km(panaji) < 10

    def test_bbox_around_a_point_spans_twice_the_radius(self):
        from scrapers.osm import _bbox_around, _bbox_span_km
        box = _bbox_around(15.49, 73.82, 55000)
        # Diagonal of a 110km square is ~155km.
        assert 140 < _bbox_span_km(box) < 175

    def test_centroids_are_spread_not_merely_the_biggest_towns(self):
        """Goa's four most populous settlements all sit near Panaji, so taking
        the top N by population would cluster — which is the very bug this
        fixes. Population picks WHICH places, distance picks WHERE."""
        from scrapers.osm import _pick_spread_centroids
        bbox = (14.75, 15.80, 73.67, 74.33)
        towns = [
            ("Panaji", 15.49, 73.82),
            ("Taleigao", 15.46, 73.84),      # 4km away — must be rejected
            ("Mapusa", 15.59, 73.81),        # 11km — still too close
            ("Margao", 15.28, 73.98),        # ~28km — accepted
            ("Palolem", 15.01, 74.02),       # ~57km — accepted
        ]
        chosen = _pick_spread_centroids((15.49, 73.82), towns, bbox)
        names = [c[0] for c in chosen]
        assert "Taleigao" not in names
        assert "Margao" in names and "Palolem" in names

    def test_centroids_outside_the_bbox_are_rejected(self):
        """A town past the border is not this destination, and would drag the
        pool across it."""
        from scrapers.osm import _pick_spread_centroids
        bbox = (14.75, 15.80, 73.67, 74.33)
        towns = [("Mumbai", 19.07, 72.87)]
        chosen = _pick_spread_centroids((15.49, 73.82), towns, bbox)
        assert [c[0] for c in chosen] == [""]     # primary only

    def test_centroid_count_is_capped(self):
        from scrapers.osm import _MAX_AREA_CENTROIDS, _pick_spread_centroids
        bbox = (0.0, 10.0, 0.0, 10.0)
        towns = [(f"T{i}", float(i), float(i)) for i in range(1, 9)]
        chosen = _pick_spread_centroids((0.0, 0.0), towns, bbox)
        assert len(chosen) <= _MAX_AREA_CENTROIDS

    def test_interleave_gives_every_area_a_share(self):
        """Concatenating and truncating would let the densest area fill the
        cap — the same starvation `_prioritize_landmarks` prevents per
        category, one dimension over."""
        from scrapers.osm import _interleave_by_area
        dense = [{"name": f"Panaji {i}"} for i in range(50)]
        sparse = [{"name": f"Palolem {i}"} for i in range(5)]
        merged = _interleave_by_area([dense, sparse], cap=10)
        assert len(merged) == 10
        assert sum(1 for p in merged if p["name"].startswith("Palolem")) == 5

    def test_interleave_preserves_ranking_within_an_area(self):
        from scrapers.osm import _interleave_by_area
        a = [{"name": "A best"}, {"name": "A second"}]
        b = [{"name": "B best"}, {"name": "B second"}]
        merged = _interleave_by_area([a, b], cap=4)
        assert [p["name"] for p in merged] == ["A best", "B best", "A second", "B second"]

    def test_interleave_dedupes_overlapping_areas(self):
        """Neighbouring radii legitimately return the same place twice, and a
        duplicate would consume a slot owed to another area."""
        from scrapers.osm import _interleave_by_area
        a = [{"name": "Se Cathedral"}, {"name": "Only in A"}]
        b = [{"name": "se cathedral"}, {"name": "Only in B"}]
        merged = _interleave_by_area([a, b], cap=10)
        names = [p["name"].lower() for p in merged]
        assert names.count("se cathedral") == 1
        assert len(merged) == 3

    def test_declared_extent_survives_hub_pinning(self):
        """Once "Goa" resolves to Panaji, every automatic size check sees a
        small town — the extent table is the only thing that still knows the
        state is 105km long."""
        from scrapers.osm import _radius_override_for
        assert _radius_override_for("Goa") == 55000


class TestIngestOutcomeIsReported:
    """🔴 Every guard returns the EXISTING stored count when it declines to
    overwrite, which makes the count ambiguous: 60 could mean 60 were just
    written, or 60 were already there and the fetch was rejected.

    A batch runner cannot tell those apart from a count, and one already got it
    wrong — the 2026-08-06 overnight re-ingestion reported 163 "ok" while 25 had
    never been re-fetched at all. Same proxy trap as the v10.40 prominence run
    reporting 169/169 complete with 29 destinations carrying no prominence
    signal.
    """

    def _pool(self) -> list[dict]:
        return [
            {"destination": "X", "name": f"POI {i}",
             "poi_type": ["attraction", "museum", "park", "beach"][i % 4],
             "lat": 1.0, "lon": 1.0, "text": f"POI {i}"}
            for i in range(60)
        ]

    async def _run(self, meta, existing):
        from scrapers.osm import ingest_osm_pois_with_outcome
        mock_qdrant = MagicMock()
        with patch("scrapers.osm._fetch_osm_pois_with_meta", new=AsyncMock(return_value=meta)), \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384] * 60), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=existing), \
             patch("scrapers.osm.delete_stale_destination_points", return_value=0):
            return await ingest_osm_pois_with_outcome("X")

    @pytest.mark.asyncio
    async def test_a_real_write_is_reported_as_written(self):
        from scrapers.osm import INGEST_WRITTEN
        count, outcome = await self._run((self._pool(), True, False), 60)
        assert (count, outcome) == (60, INGEST_WRITTEN)

    @pytest.mark.asyncio
    async def test_degraded_geocode_is_distinguishable_from_a_write(self):
        from scrapers.osm import INGEST_KEPT_DEGRADED_GEOCODE
        count, outcome = await self._run((self._pool(), True, True), 60)
        assert count == 60                       # same number as a success...
        assert outcome == INGEST_KEPT_DEGRADED_GEOCODE   # ...different meaning

    @pytest.mark.asyncio
    async def test_prominence_failure_is_distinguishable(self):
        from scrapers.osm import INGEST_KEPT_PROMINENCE_FAILED
        count, outcome = await self._run((self._pool(), False, False), 60)
        assert (count, outcome) == (60, INGEST_KEPT_PROMINENCE_FAILED)

    @pytest.mark.asyncio
    async def test_empty_fetch_with_nothing_stored(self):
        from scrapers.osm import INGEST_EMPTY_NOTHING
        count, outcome = await self._run(([], True, False), 0)
        assert (count, outcome) == (0, INGEST_EMPTY_NOTHING)

    @pytest.mark.asyncio
    async def test_the_int_wrapper_still_works_for_every_existing_caller(self):
        """A dozen scripts, the scheduler and destination_ingestion all expect
        a bare int — the richer function must not change their contract."""
        from scrapers.osm import ingest_osm_pois
        mock_qdrant = MagicMock()
        with patch("scrapers.osm._fetch_osm_pois_with_meta",
                   new=AsyncMock(return_value=(self._pool(), True, False))), \
             patch("scrapers.osm.embed", return_value=[[0.1] * 384] * 60), \
             patch("scrapers.osm.get_qdrant", return_value=mock_qdrant), \
             patch("scrapers.osm.count_destination_points", return_value=0), \
             patch("scrapers.osm.delete_stale_destination_points", return_value=0):
            result = await ingest_osm_pois("X")
        assert result == 60
        assert isinstance(result, int)
