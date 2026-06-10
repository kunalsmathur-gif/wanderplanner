'use client'

import { useEffect } from 'react'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { ItineraryItem } from '@/types'

// Fix Leaflet default marker icons broken by bundlers
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const HIGHLIGHT_ICON = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
})

function FlyToHovered({ items, hoveredId }: { items: ItineraryItem[]; hoveredId: string | null }) {
  const map = useMap()
  useEffect(() => {
    if (!hoveredId) return
    const item = items.find((i) => i.id === hoveredId)
    if (item?.location?.lat) {
      map.flyTo([item.location.lat, item.location.lon], 15, { animate: true, duration: 0.5 })
    }
  }, [hoveredId, items, map])
  return null
}

interface Props {
  items: ItineraryItem[]
  hoveredId: string | null
  center: [number, number]
}

export default function ItineraryMap({ items, hoveredId, center }: Props) {
  const validItems = items.filter((i) => i.location?.lat && i.location?.lon)

  return (
    <MapContainer
      center={center}
      zoom={13}
      style={{ width: '100%', height: '100%' }}
      scrollWheelZoom={false}
      attributionControl={false}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />
      {validItems.map((item) => (
        <Marker
          key={item.id}
          position={[item.location.lat, item.location.lon]}
          icon={item.id === hoveredId ? HIGHLIGHT_ICON : new L.Icon.Default()}
        >
          <Popup>
            <div className="text-xs max-w-[180px]">
              <p className="font-semibold text-slate-800">{item.title}</p>
              <p className="text-slate-500 mt-0.5">{item.time_start} – {item.time_end}</p>
            </div>
          </Popup>
        </Marker>
      ))}
      <FlyToHovered items={validItems} hoveredId={hoveredId} />
    </MapContainer>
  )
}
