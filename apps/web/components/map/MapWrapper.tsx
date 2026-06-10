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
  const center: [number, number] = destination?.lat
    ? [destination.lat, destination.lon]
    : [20, 78] // fallback: India centre

  return (
    <div className="h-[220px] w-full overflow-hidden rounded-lg border border-slate-200">
      <ItineraryMap items={items} hoveredId={hoveredItemId} center={center} />
    </div>
  )
}
