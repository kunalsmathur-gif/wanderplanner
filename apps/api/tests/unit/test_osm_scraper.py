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

from scrapers.osm import _prioritize_landmarks, fetch_osm_pois


def _make_element(osm_id: int, name: str, tags: dict[str, str], lat: float = 51.5, lon: float = -0.1) -> dict:
    return {"id": osm_id, "lat": lat, "lon": lon, "tags": {"name": name, **tags}}


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
    async def test_returns_empty_list_on_network_failure(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("scrapers.osm.httpx.AsyncClient", return_value=mock_client):
            pois = await fetch_osm_pois("Nowhere", lat=0.0, lon=0.0)

        assert pois == []
