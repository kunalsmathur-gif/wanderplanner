"""Deterministic multi-hop route ordering.

Multi-city trips are described by the user as a wishlist (destination +
hops), typed or picked in whatever order they thought of the places, not
necessarily the order that minimises travel time/cost between them. Left
as-is, the itinerary generator was simply handed that list order verbatim
and told to "distribute days proportionally across all stops" — so a trip
entered as Colombo, Yala, Mirissa got planned in that literal sequence even
when Mirissa sits between Colombo and Yala, forcing a needless backtrack.

This module fixes that deterministically (no LLM call, no hallucination
risk) rather than trusting the model to reason about geography: given the
traveller's origin and the set of stops (destination + hops), it picks the
visiting order that minimises total straight-line travel distance, using
the same haversine distance already used for cost/flight-band estimation
elsewhere in this codebase (core/distance_pricing.py).

Deliberately NOT used when `TripConfig.fixed_stop_order` is set — that flag
means the user gave an explicit reason to visit stops in a specific order
(e.g. a football match, a wedding, a flight already booked out of a
particular city on a particular day) and reordering would silently break
their plan. See models/trip.py's field docstring and
chains/wizard_chat_chain.py / chains/chat_refine_chain.py for where that
flag gets set from what the user actually said.
"""
from __future__ import annotations

from itertools import permutations
from typing import Sequence

from core.distance_pricing import haversine_km
from models.trip import DestinationInput, OriginInput

# Beyond ~8 stops, brute-force permutation (n!) stops being "trivial" — but
# MAX_HOPS (models/trip.py) caps hops at 5, i.e. at most 6 stops (destination
# + 5 hops) = 720 permutations, comfortably cheap. This guard exists only so
# a future MAX_HOPS increase fails loudly here instead of silently getting
# slow.
_MAX_BRUTE_FORCE_STOPS = 8


def _has_coords(stop: DestinationInput) -> bool:
    return not (stop.lat == 0.0 and stop.lon == 0.0)


def optimize_stop_order(
    origin: OriginInput | None,
    stops: Sequence[DestinationInput],
) -> list[DestinationInput]:
    """Return `stops` reordered to minimise total straight-line travel
    distance for the path origin -> stop -> stop -> ... -> stop.

    Best-effort, not exact-guarantee: only reorders stops that actually
    carry real coordinates (lat/lon both 0.0 is the "ungeocoded" sentinel
    used throughout this codebase, e.g. `_flag_out_of_bounds_items` above).
    Any stop without coordinates is left in its original relative position
    at the end of the returned list, appended after the optimized,
    geocoded stops, since there is nothing to optimize its position against.

    Returns the input order unchanged (a no-op, not an error) when there
    are fewer than 2 geocoded stops to reorder, or when the number of
    geocoded stops exceeds `_MAX_BRUTE_FORCE_STOPS`.
    """
    geocoded = [s for s in stops if _has_coords(s)]
    ungeocoded = [s for s in stops if not _has_coords(s)]

    if len(geocoded) < 2 or len(geocoded) > _MAX_BRUTE_FORCE_STOPS:
        return list(stops)

    if origin is not None and _has_coords_origin(origin):
        start_lat, start_lon = origin.lat, origin.lon
    else:
        # No usable origin to anchor the path — start from the first stop
        # as given (still optimizes the legs between the remaining stops).
        start_lat, start_lon = geocoded[0].lat, geocoded[0].lon
        first, geocoded = geocoded[0], geocoded[1:]
        best = _best_permutation(start_lat, start_lon, geocoded)
        return [first, *best, *ungeocoded]

    best = _best_permutation(start_lat, start_lon, geocoded)
    return [*best, *ungeocoded]


def _has_coords_origin(origin: OriginInput) -> bool:
    return not (origin.lat == 0.0 and origin.lon == 0.0)


def _best_permutation(
    start_lat: float, start_lon: float, stops: list[DestinationInput]
) -> list[DestinationInput]:
    """Exact brute-force minimisation of total path length starting at
    (start_lat, start_lon) and visiting every stop exactly once (open path,
    no return leg — travellers fly home from wherever they end up, not
    back through the origin)."""
    if not stops:
        return []
    if len(stops) == 1:
        return list(stops)

    best_order: list[DestinationInput] | None = None
    best_distance = float("inf")
    for perm in permutations(stops):
        total = 0.0
        lat, lon = start_lat, start_lon
        for stop in perm:
            total += haversine_km(lat, lon, stop.lat, stop.lon)
            lat, lon = stop.lat, stop.lon
            if total >= best_distance:
                break
        else:
            if total < best_distance:
                best_distance = total
                best_order = list(perm)
    return best_order if best_order is not None else list(stops)
