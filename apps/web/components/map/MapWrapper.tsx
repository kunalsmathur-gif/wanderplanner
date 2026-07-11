'use client'

import dynamic from 'next/dynamic'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'

const ItineraryMap = dynamic(() => import('./ItineraryMap'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full bg-slate-100 text-slate-400 text-xs">
      Loading map…
    </div>
  ),
})

export function MapWrapper() {
  const { days, activeDay, hoveredItemId } = useItineraryStore()
  const destination = useTripConfigStore((s) => s.config.destination)

  const items = days[activeDay]?.items ?? []
  const validItems = items.filter((i) => i.location?.lat && i.location?.lon)

  // Prefer centering on the current day's actual (resolved) stop coordinates
  // over the trip's top-level `destination` field — the latter is frequently
  // 0/0 for multi-city or country-mode trips (it's not always geocoded), which
  // previously caused the map to fall through to a hardcoded India-centre
  // fallback and render a seemingly random, unrelated town.
  const center: [number, number] = validItems.length > 0
    ? [validItems[0].location.lat, validItems[0].location.lon]
    : destination?.lat
      ? [destination.lat, destination.lon]
      : [20, 78] // last-resort fallback: India centre

  return (
    <div className="h-[220px] w-full overflow-hidden rounded-lg border border-slate-200">
      <ItineraryMap items={items} hoveredId={hoveredItemId} center={center} />
    </div>
  )
}
