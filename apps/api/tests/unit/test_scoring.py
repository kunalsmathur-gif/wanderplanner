"""Unit tests for alignment scoring (PRD Section 6.2)."""
import pytest
from models.itinerary import ItineraryItem, ItineraryItemLocation
from models.trip import TripConfig, GroupComposition, AccommodationPrefs, Budget, OriginInput
from chains.scoring import calculate_alignment_score


def _make_item(tags: list[str], description: str = "") -> ItineraryItem:
    return ItineraryItem(
        id="test",
        time_start="09:00",
        time_end="10:00",
        title="Test venue",
        description=description,
        location=ItineraryItemLocation(lat=0, lon=0, address=""),
        tags=tags,
    )


def _make_config(personas: list[str] = [], wheelchair: bool = False) -> TripConfig:
    return TripConfig(
        purpose="explore",
        dates={"start": "2026-11-13", "end": "2026-11-19", "flexible": False},
        scope="international",
        origin=OriginInput(city="Bangalore"),
        personas=personas,
        group=GroupComposition(),
        accommodation=AccommodationPrefs(wheelchair_accessible=wheelchair),
        budget=Budget(amount=100000, currency="INR"),
    )


def test_score_is_between_0_and_100():
    item = _make_item(["outdoor"])
    config = _make_config()
    score = calculate_alignment_score(item, config)
    assert 0 <= score <= 100


def test_persona_match_raises_score():
    item_matching = _make_item(["work_block", "wifi"])
    item_generic = _make_item(["outdoor"])
    config = _make_config(personas=["digital_nomad"])

    score_match = calculate_alignment_score(item_matching, config)
    score_generic = calculate_alignment_score(item_generic, config)
    assert score_match >= score_generic


def test_social_penalty_applied():
    item_clean = _make_item(["outdoor"], description="Great park")
    item_negative = _make_item(["outdoor"], description="Many visitors avoid this place")
    config = _make_config()

    score_clean = calculate_alignment_score(item_clean, config)
    score_neg = calculate_alignment_score(item_negative, config)
    assert score_clean > score_neg


def test_weights_sum_to_one():
    from chains.scoring import W_PERSONA, W_BUDGET, W_ACCESS
    assert abs((W_PERSONA + W_BUDGET + W_ACCESS) - 1.0) < 1e-9
