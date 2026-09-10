import type { DestinationInput, ItineraryDay } from '@/types'

/** Haversine distance in km — mirrors apps/api/core/distance_pricing.py's
 * `haversine_km` (same formula, independently needed here since this is a
 * frontend-only lookup with no API round-trip). */
function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLon = ((lon2 - lon1) * Math.PI) / 180
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

/**
 * Which stop (the trip's main `destination` or one of its `hops`) a given
 * itinerary day is actually about, by nearest-distance match against the
 * day's own resolved item coordinates.
 *
 * Bug fix (2026-09-10): `Column3Sidebar`'s "Best time to visit" / "Travel
 * Tips & Community" section used to always show the trip's single top-level
 * `destination.city` (e.g. "Colombo"), regardless of which day was active —
 * so a multi-hop Sri Lanka trip (Colombo -> Mirissa -> Yala -> Bentota)
 * showed Colombo tips on every day, or whichever city happened to be
 * geocoded into `destination`. `MapWrapper` already solved the equivalent
 * problem for the map (it centres on the active day's own item
 * coordinates, not the trip-level `destination`) — this reuses that same
 * "trust the day's actual locations" idea for tips/best-time instead of
 * introducing a third, differently-wrong heuristic.
 *
 * A day's items don't carry a city name (`ItineraryItemLocation` is just
 * lat/lon/address — see models/itinerary.py), so this reverse-matches the
 * day's average coordinate against the finite list of named stops the trip
 * actually has (`destination` + `hops`, all geocoded with lat/lon) rather
 * than trying to parse a city out of free-text `address` strings, which
 * vary wildly in format across destinations.
 */
export function resolveDayCity(
  day: ItineraryDay | undefined,
  destination: DestinationInput | null,
  hops: DestinationInput[],
): DestinationInput | null {
  const stops = [destination, ...hops].filter(
    (s): s is DestinationInput => !!s && typeof s.lat === 'number' && typeof s.lon === 'number' && !!s.city,
  )
  if (stops.length === 0) return null
  if (stops.length === 1) return stops[0]

  const validItems = (day?.items ?? []).filter(
    (i) => typeof i.location?.lat === 'number' && typeof i.location?.lon === 'number' && (i.location.lat || i.location.lon),
  )
  if (validItems.length === 0) return destination ?? stops[0]

  const avgLat = validItems.reduce((sum, i) => sum + i.location.lat, 0) / validItems.length
  const avgLon = validItems.reduce((sum, i) => sum + i.location.lon, 0) / validItems.length

  let nearest = stops[0]
  let nearestDistance = haversineKm(avgLat, avgLon, nearest.lat, nearest.lon)
  for (const stop of stops.slice(1)) {
    const distance = haversineKm(avgLat, avgLon, stop.lat, stop.lon)
    if (distance < nearestDistance) {
      nearest = stop
      nearestDistance = distance
    }
  }
  return nearest
}
