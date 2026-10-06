'use client'

import { useEffect } from 'react'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { DestinationCandidate } from '@/types'

// Fix Leaflet default marker icons broken by bundlers. Mirrors
// components/map/ItineraryMap.tsx's exact workaround — but L.Icon.Default's
// `.mergeOptions()` mutates the shared class prototype once per process, so
// running this twice is harmless (idempotent), not duplicated. This map is
// always lazy-loaded via `next/dynamic({ ssr: false })` the same way
// ItineraryMap is (see WorkationMapWrapper), so both copies only ever run
// client-side.
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const DESTINATION_ICON = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
})

const SELECTED_ICON = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-gold.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
})

// Smaller/distinct icon for event markers, per the plan's "map is the primary
// visual surface" requirement — events are secondary context, not selectable.
const EVENT_ICON = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-green.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [19, 31],
  iconAnchor: [9, 31],
  popupAnchor: [1, -26],
  shadowSize: [31, 31],
})

// India's rough geographic centre — reasonable default zoom/centre before any
// destinations are plotted, same "last-resort fallback" coordinate already
// used by components/map/MapWrapper.tsx.
const INDIA_CENTER: [number, number] = [22.5, 79]

function FitToDestinations({ destinations }: { destinations: DestinationCandidate[] }) {
  const map = useMap()
  useEffect(() => {
    if (destinations.length === 0) return
    const bounds = L.latLngBounds(destinations.map((d) => [d.lat, d.lon] as [number, number]))
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 8 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [destinations.map((d) => `${d.lat},${d.lon}`).join('|')])
  return null
}

interface Props {
  destinations: DestinationCandidate[]
  selectedDestination: DestinationCandidate | null
  onSelectDestination: (destination: DestinationCandidate) => void
  onPlanThisTrip: (destination: DestinationCandidate) => void
}

export default function WorkationMap({ destinations, selectedDestination, onSelectDestination, onPlanThisTrip }: Props) {
  // Defensive safety net per the plan — the backend already drops
  // ungeocodable destinations/events, but never trust lat/lon blindly on the
  // rendering side either.
  const validDestinations = destinations.filter((d) => Number.isFinite(d.lat) && Number.isFinite(d.lon))
  const events = validDestinations.flatMap((d) => d.matching_events)
  const validEvents = events.filter((e) => Number.isFinite(e.lat) && Number.isFinite(e.lon))

  return (
    <MapContainer
      center={INDIA_CENTER}
      zoom={5}
      style={{ width: '100%', height: '100%' }}
      scrollWheelZoom={true}
      attributionControl={false}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />
      {validDestinations.map((destination) => (
        <Marker
          key={destination.destination}
          position={[destination.lat, destination.lon]}
          icon={destination.destination === selectedDestination?.destination ? SELECTED_ICON : DESTINATION_ICON}
          eventHandlers={{ click: () => onSelectDestination(destination) }}
        >
          <Popup>
            <div className="max-w-[220px] text-xs">
              <p className="font-semibold text-slate-800">{destination.destination}</p>
              <p className="mt-1 text-slate-600">{destination.rationale}</p>
              <p className="mt-1.5 font-medium text-slate-700">{destination.workation_split}</p>
              <button
                type="button"
                onClick={() => onPlanThisTrip(destination)}
                className="mt-2 w-full rounded-lg bg-[var(--_primary)] px-2.5 py-1.5 text-xs font-semibold text-white"
              >
                Plan this trip
              </button>
            </div>
          </Popup>
        </Marker>
      ))}
      {validEvents.map((event, idx) => (
        <Marker key={`${event.name}-${idx}`} position={[event.lat, event.lon]} icon={EVENT_ICON}>
          <Popup>
            <div className="max-w-[200px] text-xs">
              <p className="font-semibold text-slate-800">{event.name}</p>
              <p className="mt-0.5 text-slate-500">{event.start_date} – {event.end_date}</p>
              <p className="text-slate-500">{event.location}</p>
            </div>
          </Popup>
        </Marker>
      ))}
      <FitToDestinations destinations={validDestinations} />
    </MapContainer>
  )
}
