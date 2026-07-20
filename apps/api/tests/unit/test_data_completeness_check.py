"""Unit tests for the data-completeness pre-flight gate (GTM item 13,
2026-07-20): scoring thresholds in `eval/data_completeness_scoring.py` and
the runner's destination-check wiring in
`eval/run_data_completeness_check.py`. Qdrant is mocked — fully offline,
same as the other eval unit-test suites; this module's whole purpose is to
be run for real against production (see the runner's own docstring), not to
replace that with an offline test.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from eval.data_completeness_scoring import (
    MAX_CATEGORY_SHARE,
    MIN_OSM_POIS,
    MIN_WIKI_CHUNKS,
    aggregate,
    score_destination,
)
from eval.run_data_completeness_check import check_destination, golden_destinations

REFINEMENT_DATASET_PATH = Path(__file__).parents[2] / "eval" / "refinement_fidelity_dataset.json"


def _pois(category_counts: dict[str, int]) -> list[dict]:
    pois = []
    for category, count in category_counts.items():
        pois.extend({"poi_type": category, "name": f"{category} {i}"} for i in range(count))
    return pois


class TestScoreDestination:
    def test_healthy_destination_passes(self):
        pois = _pois({"museum": 10, "restaurant": 10, "park": 10})
        result = score_destination("London", wiki_chunk_count=5, osm_pois=pois)
        assert result["passed"]
        assert result["failures"] == []
        assert result["osm_poi_count"] == 30
        assert result["wiki_chunk_count"] == 5

    def test_zero_wiki_chunks_fails(self):
        pois = _pois({"museum": MIN_OSM_POIS})
        result = score_destination("London", wiki_chunk_count=0, osm_pois=pois)
        assert not result["passed"]
        assert any("wiki_chunk_count" in f for f in result["failures"])

    def test_below_minimum_osm_pois_fails(self):
        pois = _pois({"museum": MIN_OSM_POIS - 1})
        result = score_destination("London", wiki_chunk_count=MIN_WIKI_CHUNKS, osm_pois=pois)
        assert not result["passed"]
        assert any("osm_poi_count" in f for f in result["failures"])

    def test_category_starvation_fails(self):
        # Regression shape for the exact 2026-07-20 bug: London's 58 real OSM
        # POIs were 58/58 food/drink — one category dominating entirely.
        pois = _pois({"restaurant": 50, "cafe": 8})
        result = score_destination("London", wiki_chunk_count=MIN_WIKI_CHUNKS, osm_pois=pois)
        assert not result["passed"]
        assert any("top_category" in f for f in result["failures"])
        assert result["top_category"] == "restaurant"
        assert result["top_category_share"] > MAX_CATEGORY_SHARE

    def test_category_share_at_threshold_boundary_passes(self):
        # Exactly at the threshold should not fail (share > threshold fails,
        # share == threshold is allowed).
        pois = _pois({"museum": 10, "restaurant": 10})  # 50/50 split
        result = score_destination("London", wiki_chunk_count=MIN_WIKI_CHUNKS, osm_pois=pois)
        assert result["top_category_share"] == 0.5
        assert result["passed"]

    def test_missing_poi_type_bucketed_as_unknown(self):
        pois = [{"name": "Mystery Place"} for _ in range(MIN_OSM_POIS)]
        result = score_destination("London", wiki_chunk_count=MIN_WIKI_CHUNKS, osm_pois=pois)
        assert result["category_counts"] == {"unknown": MIN_OSM_POIS}

    def test_empty_osm_pois_does_not_crash(self):
        result = score_destination("Nowhere", wiki_chunk_count=0, osm_pois=[])
        assert result["osm_poi_count"] == 0
        assert result["top_category"] is None
        assert result["top_category_share"] == 0.0
        assert not result["passed"]


class TestAggregate:
    def test_aggregate_summarizes_pass_fail(self):
        results = [
            score_destination("A", MIN_WIKI_CHUNKS, _pois({"museum": 10, "park": 10})),
            score_destination("B", 0, _pois({"restaurant": MIN_OSM_POIS})),
        ]
        summary = aggregate(results)
        assert summary["total"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["failing_destinations"] == ["B"]

    def test_aggregate_empty_results(self):
        summary = aggregate([])
        assert summary == {
            "total": 0, "passed": 0, "failed": 0, "pass_rate": 0.0,
            "failing_destinations": [],
        }


class TestGoldenDestinations:
    def test_matches_refinement_dataset_destinations(self):
        data = json.loads(REFINEMENT_DATASET_PATH.read_text(encoding="utf-8"))
        expected = []
        for case in data["cases"]:
            if case["destination"] not in expected:
                expected.append(case["destination"])
        assert golden_destinations() == expected

    def test_no_duplicates(self):
        dests = golden_destinations()
        assert len(dests) == len(set(dests))


class TestCheckDestination:
    def test_check_destination_scrolls_both_collections(self):
        client = MagicMock()

        def _scroll(collection_name, scroll_filter, limit, with_payload, with_vectors):
            if "wiki" in collection_name:
                return [MagicMock(payload={"text": "chunk"})], None
            half = MIN_OSM_POIS // 2
            return [
                *[MagicMock(payload={"poi_type": "museum"}) for _ in range(half)],
                *[MagicMock(payload={"poi_type": "park"}) for _ in range(MIN_OSM_POIS - half)],
            ], None

        client.scroll.side_effect = _scroll
        result = check_destination(client, "London")
        assert result["destination"] == "London"
        assert result["wiki_chunk_count"] == 1
        assert result["osm_poi_count"] == MIN_OSM_POIS
        assert result["passed"]
