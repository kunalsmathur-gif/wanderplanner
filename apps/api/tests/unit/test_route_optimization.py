"""Tests for core/route_optimization.py — deterministic multi-hop stop
reordering."""
from __future__ import annotations

from core.route_optimization import optimize_stop_order
from models.trip import DestinationInput, OriginInput


def _stop(city: str, lat: float, lon: float) -> DestinationInput:
    return DestinationInput(city=city, country="", lat=lat, lon=lon)


class TestOptimizeStopOrder:
    def test_reorders_out_of_order_stops_for_shortest_path(self):
        # Real prod-shaped case: Colombo (origin-ish) -> Yala -> Mirissa as
        # typed, but Mirissa sits geographically between Colombo and Yala.
        colombo = OriginInput(city="Colombo", lat=6.9271, lon=79.8612)
        mirissa = _stop("Mirissa", 5.9483, 80.4589)
        yala = _stop("Yala", 6.3728, 81.5165)

        ordered = optimize_stop_order(colombo, [yala, mirissa])

        assert [s.city for s in ordered] == ["Mirissa", "Yala"]

    def test_noop_for_single_stop(self):
        origin = OriginInput(city="Delhi", lat=28.6139, lon=77.2090)
        agra = _stop("Agra", 27.1767, 78.0081)

        ordered = optimize_stop_order(origin, [agra])

        assert ordered == [agra]

    def test_noop_when_no_stops(self):
        origin = OriginInput(city="Delhi", lat=28.6139, lon=77.2090)
        assert optimize_stop_order(origin, []) == []

    def test_ungeocoded_stops_left_untouched_at_end(self):
        origin = OriginInput(city="Colombo", lat=6.9271, lon=79.8612)
        mirissa = _stop("Mirissa", 5.9483, 80.4589)
        yala = _stop("Yala", 6.3728, 81.5165)
        no_coords = _stop("Somewhere", 0.0, 0.0)

        ordered = optimize_stop_order(origin, [yala, mirissa, no_coords])

        assert [s.city for s in ordered] == ["Mirissa", "Yala", "Somewhere"]

    def test_no_origin_anchors_on_first_stop_and_optimizes_the_rest(self):
        yala = _stop("Yala", 6.3728, 81.5165)
        mirissa = _stop("Mirissa", 5.9483, 80.4589)
        colombo = _stop("Colombo", 6.9271, 79.8612)

        # No origin coordinates given — first stop as listed anchors the
        # path, remaining stops are still optimized against it.
        blank_origin = OriginInput()
        ordered = optimize_stop_order(blank_origin, [yala, mirissa, colombo])

        assert ordered[0].city == "Yala"
        assert {s.city for s in ordered[1:]} == {"Mirissa", "Colombo"}

    def test_three_stops_already_optimal_unchanged(self):
        colombo = OriginInput(city="Colombo", lat=6.9271, lon=79.8612)
        mirissa = _stop("Mirissa", 5.9483, 80.4589)
        yala = _stop("Yala", 6.3728, 81.5165)

        ordered = optimize_stop_order(colombo, [mirissa, yala])

        assert [s.city for s in ordered] == ["Mirissa", "Yala"]

    def test_returns_new_list_not_same_object_identity(self):
        origin = OriginInput(city="Colombo", lat=6.9271, lon=79.8612)
        stops = [_stop("Mirissa", 5.9483, 80.4589)]
        ordered = optimize_stop_order(origin, stops)
        assert ordered is not stops
