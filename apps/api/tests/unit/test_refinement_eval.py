"""
Unit tests for the refinement-fidelity eval suite (GTM Phase 1 kill-criterion
gate): dataset consistency against the REAL verification code, the scoring
math in eval/refinement_scoring.py, baseline scoring, and report rendering.
Fully offline — Qdrant is mocked with the dataset's own fixture truth-set.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from chains.itinerary_chain import _mock_itinerary
from eval.refinement_scoring import (
    aggregate,
    aggregate_baseline,
    matched_references,
    render_report,
    score_baseline_case,
    score_negative_case,
    score_positive_case,
)
from models.trip import DestinationInput, PinnedPOI, TripConfig
from services.poi_pinning import verify_candidates_sync

DATASET_PATH = Path(__file__).parents[2] / "eval" / "refinement_fidelity_dataset.json"


@pytest.fixture(scope="module")
def dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def _mock_qdrant_for(dataset: dict, destination: str) -> MagicMock:
    """In-memory stand-in seeded with the dataset fixtures for one
    destination — same scroll contract services/gems._scroll_destination uses."""
    pois = [p for p in dataset["fixtures"]["osm_pois"] if p["destination"] == destination]
    wiki = [c for c in dataset["fixtures"]["wiki"] if c["destination"] == destination]
    client = MagicMock()

    def _scroll(collection_name, scroll_filter, limit, with_payload, with_vectors):
        payloads = pois if collection_name == "osm_pois" else wiki
        points = []
        for payload in payloads:
            pt = MagicMock()
            pt.payload = payload
            points.append(pt)
        return points, None

    client.scroll.side_effect = _scroll
    return client


def _verify(dataset: dict, case: dict) -> tuple[list[PinnedPOI], list[str]]:
    with patch(
        "services.poi_pinning.get_qdrant",
        return_value=_mock_qdrant_for(dataset, case["destination"]),
    ):
        return verify_candidates_sync(
            case["offline_candidates"], case["destination"],
            source_interest=case["named_interest"],
        )


class TestDatasetConsistency:
    def test_shape(self, dataset):
        cases = dataset["cases"]
        assert len(cases) == 20
        assert len({c["id"] for c in cases}) == 20
        assert sum(1 for c in cases if c["negative"]) == 4
        for case in cases:
            assert case["destination"] and case["user_message"] and case["named_interest"]
            if case["negative"]:
                assert case["expected_pois"] == []
            else:
                assert len(case["expected_pois"]) >= 2

    def test_positive_cases_fully_verifiable(self, dataset):
        """Every expected POI must survive the REAL verification path against
        the fixture truth-set — the eval's ceiling must be a perfect score."""
        for case in dataset["cases"]:
            if case["negative"]:
                continue
            pins, _dropped = _verify(dataset, case)
            pin_names = [p.name for p in pins]
            matched = matched_references(pin_names, case["expected_pois"])
            assert matched == set(case["expected_pois"]), (
                f"{case['id']}: expected {case['expected_pois']}, verified {pin_names}"
            )

    def test_positive_cases_drop_the_invented_candidate(self, dataset):
        """Each positive case carries one invented candidate to prove the
        hallucination guard fires; it must never verify."""
        for case in dataset["cases"]:
            if case["negative"]:
                continue
            pins, dropped = _verify(dataset, case)
            assert dropped, f"{case['id']}: expected at least one dropped candidate"
            assert len(pins) == len(case["expected_pois"])

    def test_negative_cases_pin_nothing(self, dataset):
        for case in dataset["cases"]:
            if not case["negative"]:
                continue
            pins, dropped = _verify(dataset, case)
            assert pins == [], f"{case['id']}: negative case verified {pins}"
            assert len(dropped) == len(case["offline_candidates"])

    def test_osm_pins_carry_fixture_coordinates(self, dataset):
        case = next(c for c in dataset["cases"] if c["id"] == "RF-001")
        pins, _ = _verify(dataset, case)
        by_name = {p.name: p for p in pins}
        studio = by_name["Warner Bros. Studio Tour London"]
        assert studio.verified_by == "osm"
        assert studio.lat == pytest.approx(51.6906)
        platform = next(p for p in pins if "Platform" in p.name)
        assert platform.verified_by == "wiki"
        assert platform.lat == 0.0


def _items(*titles_tags: tuple[str, list[str]]) -> list[dict]:
    return [{"title": t, "tags": tags} for t, tags in titles_tags]


class TestScoringMath:
    CASE = {
        "id": "T-1", "destination": "London", "named_interest": "Harry Potter",
        "expected_pois": ["Warner Bros. Studio Tour London", "Leadenhall Market"],
        "negative": False,
    }

    def test_perfect_case_scores_one(self):
        pins = ["Warner Bros. Studio Tour London", "Leadenhall Market"]
        items = _items(
            ("Warner Bros. Studio Tour London", ["experience", "pinned"]),
            ("Leadenhall Market", ["experience", "pinned"]),
            ("British Museum", ["culture"]),
        )
        r = score_positive_case(self.CASE, pins, pins, items, items)
        assert r["pin_recall"] == 1.0
        assert r["pin_precision"] == 1.0
        assert r["inclusion_rate"] == 1.0
        assert r["stability_rate"] == 1.0
        assert r["fidelity"] == pytest.approx(1.0)

    def test_missing_pin_halves_recall(self):
        pins = ["Leadenhall Market"]
        items = _items(("Leadenhall Market", ["pinned"]))
        r = score_positive_case(self.CASE, pins, pins, items, items)
        assert r["pin_recall"] == 0.5
        assert r["inclusion_rate"] == 1.0

    def test_inclusion_requires_pinned_tag(self):
        pins = ["Leadenhall Market"]
        items = _items(("Leadenhall Market", ["experience"]))  # present but untagged
        r = score_positive_case(self.CASE, pins, pins, items, items)
        assert r["inclusion_rate"] == 0.0
        assert r["stability_rate"] == 1.0  # stability only needs presence

    def test_inclusion_requires_exactly_once(self):
        pins = ["Leadenhall Market"]
        items = _items(
            ("Leadenhall Market", ["pinned"]),
            ("Leadenhall Market", ["pinned"]),
        )
        r = score_positive_case(self.CASE, pins, pins, items, items)
        assert r["inclusion_rate"] == 0.0

    def test_dropped_pin_breaks_stability(self):
        pins = ["Leadenhall Market"]
        items = _items(("Leadenhall Market", ["pinned"]))
        r = score_positive_case(self.CASE, pins, pins, items, _items(("Louvre", ["art"])))
        assert r["stability_rate"] == 0.0

    def test_off_target_pin_lowers_precision(self):
        pins = ["Leadenhall Market", "London Eye"]
        items = _items(("Leadenhall Market", ["pinned"]), ("London Eye", ["pinned"]))
        r = score_positive_case(self.CASE, pins, pins, items, items)
        assert r["pin_precision"] == 0.5

    def test_no_pins_scores_zero(self):
        r = score_positive_case(self.CASE, [], [], [], [])
        assert r["fidelity"] == 0.0
        assert r["pin_precision"] == 0.0

    def test_fuzzy_title_match_counts(self):
        pins = ["Warner Bros. Studio Tour London", "Leadenhall Market"]
        items = _items(
            ("Warner Bros Studio Tour", ["pinned"]),   # punctuation/suffix variance
            ("Leadenhall Market", ["pinned"]),
        )
        r = score_positive_case(self.CASE, pins, pins, items, items)
        assert r["inclusion_rate"] == 1.0


class TestNegativeScoring:
    CASE = {
        "id": "T-N", "destination": "Goa", "named_interest": "Harry Potter",
        "expected_pois": [], "negative": True,
        "offline_candidates": ["Hogwarts Beach Resort"],
    }

    def test_honest_when_nothing_pinned_or_leaked(self):
        r = score_negative_case(self.CASE, [], _items(("Baga Beach", ["beach"])))
        assert r["honest"] is True

    def test_dishonest_when_pinned(self):
        r = score_negative_case(self.CASE, ["Hogwarts Beach Resort"], [])
        assert r["honest"] is False

    def test_dishonest_when_invented_place_leaks_into_itinerary(self):
        r = score_negative_case(self.CASE, [], _items(("Hogwarts Beach Resort", ["fun"])))
        assert r["honest"] is False
        assert r["leaked"] == ["Hogwarts Beach Resort"]


class TestBaselineScoring:
    CASE = {
        "id": "T-B", "destination": "London", "named_interest": "Harry Potter",
        "expected_pois": ["Warner Bros. Studio Tour London", "Leadenhall Market"],
        "negative": False,
    }
    FIXTURES = ["Warner Bros. Studio Tour London", "Leadenhall Market", "London Eye"]

    def test_verified_recall_and_unverifiable_rate(self):
        places = ["Warner Bros. Studio Tour", "The Hogwarts Pub", "London Eye"]
        r = score_baseline_case(self.CASE, places, self.FIXTURES)
        assert r["verified_recall"] == 0.5           # studio matched, market missed
        assert r["unverifiable_rate"] == pytest.approx(1 / 3)  # only the invented pub

    def test_negative_baseline_honesty(self):
        neg = {**self.CASE, "negative": True, "expected_pois": []}
        assert score_baseline_case(neg, [], self.FIXTURES)["honest"] is True
        assert score_baseline_case(neg, ["Wizard World Goa"], self.FIXTURES)["honest"] is False

    def test_empty_places_zero_scores(self):
        r = score_baseline_case(self.CASE, [], self.FIXTURES)
        assert r["verified_recall"] == 0.0
        assert r["unverifiable_rate"] == 0.0


class TestAggregationAndReport:
    def _results(self):
        pos = {
            "id": "A", "destination": "X", "interest": "i", "negative": False,
            "expansion_recall": 1.0, "pin_recall": 1.0, "pin_precision": 1.0,
            "inclusion_rate": 1.0, "stability_rate": 0.5, "fidelity": 0.9, "pins": ["P"],
        }
        neg = {"id": "B", "destination": "Y", "interest": "j", "negative": True,
               "honest": True, "pins": [], "leaked": []}
        return [pos, neg]

    def test_aggregate(self):
        agg = aggregate(self._results())
        assert agg["n_positive"] == 1 and agg["n_negative"] == 1
        assert agg["fidelity"] == 0.9
        assert agg["honesty_rate"] == 1.0

    def test_aggregate_baseline(self):
        results = [
            {"id": "A", "negative": False, "verified_recall": 0.5,
             "unverifiable_rate": 0.25, "places": ["x"]},
            {"id": "B", "negative": True, "honest": False, "places": ["y"]},
        ]
        agg = aggregate_baseline(results)
        assert agg["verified_recall"] == 0.5
        assert agg["honesty_rate"] == 0.0

    def test_report_renders_headline_and_baseline_table(self):
        results = self._results()
        agg = aggregate(results)
        baseline = [{"id": "A", "negative": False, "verified_recall": 0.4,
                     "unverifiable_rate": 0.3, "places": []}]
        report = render_report(results, agg, "offline-replay",
                               baseline, aggregate_baseline(baseline))
        assert "Refinement fidelity score" in report
        assert "vs ChatGPT baseline" in report
        assert "| A | X | i |" in report


class TestEndToEndOfflineSlice:
    """RF-001 through verification + mock generation — the exact offline
    pipeline slice the runner scores, without the runner's process-level
    setup (in-memory Qdrant seeding is exercised there, mocked here)."""

    def test_rf001_full_offline_slice(self, dataset):
        case = next(c for c in dataset["cases"] if c["id"] == "RF-001")
        pins, dropped = _verify(dataset, case)
        assert dropped == ["The Hogwarts Express Terminal"]

        trip = TripConfig(
            destination=DestinationInput(city="London", country="United Kingdom",
                                         lat=51.5074, lon=-0.1278),
            pinned_pois=pins,
        )
        raw = _mock_itinerary(trip)
        items = [{"title": i["title"], "tags": i["tags"]}
                 for d in raw["days"] for i in d["items"]]

        relaxed = trip.model_copy(update={"pace": "relaxed"})
        refined_raw = _mock_itinerary(relaxed)
        refined_items = [{"title": i["title"], "tags": i["tags"]}
                         for d in refined_raw["days"] for i in d["items"]]

        result = score_positive_case(
            case, case["offline_candidates"], [p.name for p in pins],
            items, refined_items,
        )
        assert result["pin_recall"] == 1.0
        assert result["inclusion_rate"] == 1.0
        assert result["stability_rate"] == 1.0
        assert result["fidelity"] == pytest.approx(1.0)
