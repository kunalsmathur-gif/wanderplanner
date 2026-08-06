"""Regression tests for itinerary_chain.py's enforcement pass: out-of-bounds
and likely-fabricated items must be actively removed from the itinerary
(not merely flagged), while a genuinely sparse destination corpus must keep
the safe "unverified but present" fallback.

Covers docs/agents' latest policy request:
- Out-of-bounds items: always dropped (never left for the user to keep).
- Unverified item, destination corpus well-populated: dropped (treated as
  fabricated — the model invented a specific place).
- Unverified item, destination corpus thin: kept, tagged verified=False
  (the safe LLM-fallback case — the place may be real, just unmapped).
- Pinned items are exempt from both drops (already independently verified
  by _enforce_pins/poi_pinning.verify_candidates before this point).
"""
from __future__ import annotations

import uuid

import pytest

from chains.itinerary_chain import _flag_out_of_bounds_items, _flag_unverified_items
from models.itinerary import ItineraryDay, ItineraryItem, ItineraryItemLocation
from models.trip import DestinationInput, TripConfig


def _item(title: str, lat: float, lon: float, tags: list[str] | None = None) -> ItineraryItem:
    return ItineraryItem(
        id=str(uuid.uuid4()),
        time_start="09:00",
        time_end="11:00",
        title=title,
        description="",
        location=ItineraryItemLocation(lat=lat, lon=lon, address=""),
        tags=tags or [],
    )


def _trip_config(**kwargs) -> TripConfig:
    return TripConfig(
        destination=DestinationInput(city="Paris", country="France", lat=48.8566, lon=2.3522),
        **kwargs,
    )


class TestOutOfBoundsEnforcement:
    def test_drops_out_of_bounds_item(self):
        trip_config = _trip_config()
        days = [ItineraryDay(
            day_number=1, date="2026-01-01", theme="Day 1",
            items=[
                _item("Eiffel Tower", 48.8584, 2.2945),
                # ~9,600km from Paris — the observed live failure mode.
                _item("Warner Bros Studio Tour, London", -6.2088, 106.8456),
            ],
        )]

        result_days, dropped = _flag_out_of_bounds_items(days, trip_config)

        titles = [i.title for i in result_days[0].items]
        assert "Eiffel Tower" in titles
        assert "Warner Bros Studio Tour, London" not in titles
        assert dropped == ["Warner Bros Studio Tour, London"]

    def test_pinned_item_never_dropped_even_if_out_of_bounds(self):
        trip_config = _trip_config()
        days = [ItineraryDay(
            day_number=1, date="2026-01-01", theme="Day 1",
            items=[_item("Far Pin", -6.2088, 106.8456, tags=["pinned"])],
        )]

        result_days, dropped = _flag_out_of_bounds_items(days, trip_config)

        assert len(result_days[0].items) == 1
        assert dropped == []

    def test_zero_coordinate_item_kept_unflagged(self):
        trip_config = _trip_config()
        days = [ItineraryDay(
            day_number=1, date="2026-01-01", theme="Day 1",
            items=[_item("Mystery Spot", 0.0, 0.0)],
        )]

        result_days, dropped = _flag_out_of_bounds_items(days, trip_config)

        assert len(result_days[0].items) == 1
        assert dropped == []

    def test_no_anchors_returns_days_unchanged(self):
        trip_config = TripConfig(destination=DestinationInput(city="Nowhere"))
        days = [ItineraryDay(
            day_number=1, date="2026-01-01", theme="Day 1",
            items=[_item("Some Place", -6.2088, 106.8456)],
        )]

        result_days, dropped = _flag_out_of_bounds_items(days, trip_config)

        assert len(result_days[0].items) == 1
        assert dropped == []


class TestUnverifiedItemEnforcement:
    @pytest.mark.asyncio
    async def test_drops_item_when_corpus_well_populated(self, monkeypatch):
        """Well-covered destination, item still unmatched: treat as
        fabricated and drop it."""
        async def fake_verify(titles, destination):
            return set(), True  # nothing verified, corpus IS populated

        monkeypatch.setattr(
            "services.poi_pinning.verify_item_titles", fake_verify
        )
        trip_config = _trip_config()
        days = [ItineraryDay(
            day_number=1, date="2026-01-01", theme="Day 1",
            items=[_item("Wizarding World of Goa", 15.2993, 74.1240)],
        )]

        result_days, dropped = await _flag_unverified_items(days, trip_config)

        assert result_days[0].items == []
        assert dropped == ["Wizarding World of Goa"]

    @pytest.mark.asyncio
    async def test_keeps_item_when_corpus_sparse(self, monkeypatch):
        """Thin destination corpus, item unmatched: keep it, tag
        verified=False — the safe LLM-fallback case."""
        async def fake_verify(titles, destination):
            return set(), False  # nothing verified, corpus is thin

        monkeypatch.setattr(
            "services.poi_pinning.verify_item_titles", fake_verify
        )
        trip_config = _trip_config()
        days = [ItineraryDay(
            day_number=1, date="2026-01-01", theme="Day 1",
            items=[_item("Local Hidden Cafe", 15.2993, 74.1240)],
        )]

        result_days, dropped = await _flag_unverified_items(days, trip_config)

        assert len(result_days[0].items) == 1
        assert result_days[0].items[0].verified is False
        assert dropped == []

    @pytest.mark.asyncio
    async def test_verified_item_kept_regardless_of_corpus_size(self, monkeypatch):
        async def fake_verify(titles, destination):
            return set(titles), True

        monkeypatch.setattr(
            "services.poi_pinning.verify_item_titles", fake_verify
        )
        trip_config = _trip_config()
        days = [ItineraryDay(
            day_number=1, date="2026-01-01", theme="Day 1",
            items=[_item("Eiffel Tower", 48.8584, 2.2945)],
        )]

        result_days, dropped = await _flag_unverified_items(days, trip_config)

        assert len(result_days[0].items) == 1
        assert result_days[0].items[0].verified is True
        assert dropped == []

    @pytest.mark.asyncio
    async def test_pinned_item_never_checked_or_dropped(self, monkeypatch):
        async def fake_verify(titles, destination):
            raise AssertionError("pinned items must not be sent for verification")

        monkeypatch.setattr(
            "services.poi_pinning.verify_item_titles", fake_verify
        )
        trip_config = _trip_config()
        days = [ItineraryDay(
            day_number=1, date="2026-01-01", theme="Day 1",
            items=[_item("Pinned Spot", 48.8584, 2.2945, tags=["pinned"])],
        )]

        result_days, dropped = await _flag_unverified_items(days, trip_config)

        assert len(result_days[0].items) == 1
        assert dropped == []
