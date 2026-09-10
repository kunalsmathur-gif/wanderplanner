"""Tests for chains/itinerary_chain.py's `_visit_order_guidance_block` —
the prompt-injection point that tells the itinerary LLM what sequence to
visit multi-hop stops in (see core/route_optimization.py for the "why").
"""
from __future__ import annotations

from chains.itinerary_chain import _visit_order_guidance_block
from models.trip import DestinationInput, OriginInput, TripConfig


def _stop(city: str, lat: float, lon: float) -> DestinationInput:
    return DestinationInput(city=city, country="", lat=lat, lon=lon)


class TestVisitOrderGuidanceBlock:
    def test_empty_for_single_destination_trip(self):
        config = TripConfig(
            destination=_stop("Bali", -8.4095, 115.1889),
            hops=[],
        )
        assert _visit_order_guidance_block(config) == ""

    def test_reorders_when_not_fixed(self):
        config = TripConfig(
            origin=OriginInput(city="Colombo", lat=6.9271, lon=79.8612),
            destination=_stop("Colombo", 6.9271, 79.8612),
            hops=[_stop("Yala", 6.3728, 81.5165), _stop("Mirissa", 5.9483, 80.4589)],
            fixed_stop_order=False,
        )
        block = _visit_order_guidance_block(config)
        assert "VISIT ORDER:" in block
        assert "Colombo → Mirissa → Yala" in block
        assert "optimized for travel efficiency" in block

    def test_preserves_given_order_when_fixed(self):
        config = TripConfig(
            origin=OriginInput(city="Colombo", lat=6.9271, lon=79.8612),
            destination=_stop("Colombo", 6.9271, 79.8612),
            hops=[_stop("Yala", 6.3728, 81.5165), _stop("Mirissa", 5.9483, 80.4589)],
            fixed_stop_order=True,
        )
        block = _visit_order_guidance_block(config)
        assert "Colombo → Yala → Mirissa" in block
        assert "Do NOT reorder it" in block

    def test_empty_when_only_one_geocoded_stop_total(self):
        config = TripConfig(destination=_stop("Colombo", 6.9271, 79.8612), hops=[])
        assert _visit_order_guidance_block(config) == ""
