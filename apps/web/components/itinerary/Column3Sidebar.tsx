'use client'

import { useEffect, useState } from 'react'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useWizardChatStore } from '@/store/wizardChatStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { getTravelTips, type TravelTip } from '@/lib/api'
import { resolveDayCity } from '@/lib/dayLocation'
import { MapWrapper } from '@/components/map/MapWrapper'
import { BestTimeWidget } from '@/components/dashboard/BestTimeWidget'

export function Column3Sidebar() {
  const collectedLabels = useWizardChatStore((state) => state.collectedLabels)
  const configDestination = useTripConfigStore((state) => state.config.destination)
  const destinationCountry = useTripConfigStore((state) => state.config.destination_country ?? '')
  const hops = useTripConfigStore((state) => state.config.hops)
  const days = useItineraryStore((state) => state.days)
  const activeDay = useItineraryStore((state) => state.activeDay)

  // Bug fix (2026-09-10): this used to always resolve to the trip's single
  // top-level destination (or the first hop the LLM happened to write into
  // `destination`), so every day of a multi-hop trip showed tips/best-time
  // for the same one city — MapWrapper already gets this right by centring
  // on the ACTIVE DAY's own item coordinates instead, so `resolveDayCity`
  // reuses that same logic to pick whichever of destination/hops is
  // actually nearest to what the active day's items resolved to. Falls back
  // to the old trip-level fields when there's no itinerary yet (wizard/
  // pre-generation) or no day-item coordinates to match against.
  const dayCity = days.length > 0 ? resolveDayCity(days[activeDay], configDestination, hops) : null
  const destination =
    dayCity?.city || collectedLabels.destination || configDestination?.city || destinationCountry
  const [tips, setTips] = useState<TravelTip[]>([])
  const [loadingTips, setLoadingTips] = useState(false)

  useEffect(() => {
    let cancelled = false

    if (!destination) {
      setTips([])
      setLoadingTips(false)
      return
    }

    setLoadingTips(true)

    getTravelTips(destination)
      .then((data) => {
        if (!cancelled) setTips(data)
      })
      .catch(() => { if (!cancelled) setTips([]) })
      .finally(() => { if (!cancelled) setLoadingTips(false) })

    return () => { cancelled = true }
  }, [destination])


  return (
    <div className="space-y-4 p-4">
      <MapWrapper />

      {destination && (
        <div className="border-t border-[var(--_border)] pt-2">
          <BestTimeWidget destination={destination} />
        </div>
      )}

      {/* "Book This Trip" and "My Bookings" moved to the Booking & Expenses
          panel in v10.56.0 — they are purchase actions, not orientation
          material, and grouping them with expenses matches how users move
          through the plan. This section is now map + when-to-go + what-locals-
          say only. */}

      <div className="border-t border-[var(--_border)] pt-2">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-widest text-[var(--_muted-fg)]">
          Travel Tips &amp; Community{destination ? ` — ${destination}` : ''}
        </h4>

        {!destination ? (
          <p className="text-xs text-[var(--_muted-fg)]">No destination selected.</p>
        ) : loadingTips ? (
          <div className="space-y-2">
            <TipSkeletonCard />
            <TipSkeletonCard />
          </div>
        ) : tips.length === 0 ? (
          <p className="text-xs text-[var(--_muted-fg)]">No tips found for this destination yet.</p>
        ) : (
          <div className="space-y-2">
            {tips.map((tip, idx) => (
              <div
                key={`${tip.title}-${idx}`}
                className="overflow-hidden rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-3"
              >
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <span className="rounded-full bg-[var(--_muted)] px-2 py-0.5 text-[11px] font-semibold text-[var(--_primary)]">
                    {tip.source}
                  </span>
                  {tip.score > 0 && (
                    <span className="text-[11px] font-medium text-[var(--_muted-fg)]">↑ {tip.score}</span>
                  )}
                </div>
                <p className="line-clamp-2 text-sm font-semibold text-[var(--_fg)]">{tip.title}</p>
                {tip.text_preview && (
                  <p className="mt-1 line-clamp-3 text-xs text-[var(--_muted-fg)]">{tip.text_preview}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function TipSkeletonCard() {
  return (
    <div className="space-y-2 rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-3">
      <div className="h-4 w-20 animate-pulse rounded-full bg-[var(--_muted)]" />
      <div className="h-4 w-full animate-pulse rounded bg-[var(--_muted)]" />
      <div className="h-4 w-4/5 animate-pulse rounded bg-[var(--_muted)]" />
    </div>
  )
}
