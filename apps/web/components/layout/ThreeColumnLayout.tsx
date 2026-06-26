'use client'

import { useAppStore } from '@/store/appStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { Column1Metrics } from '@/components/dashboard/Column1Metrics'
import { ItineraryTimeline } from '@/components/itinerary/ItineraryTimeline'
import { Column3Sidebar } from '@/components/itinerary/Column3Sidebar'
import { ComparisonPanel } from '@/components/comparison/ComparisonPanel'
import { MapWrapper } from '@/components/map/MapWrapper'
import { ShareButton } from '@/components/common/ShareButton'

export function ThreeColumnLayout() {
  const step3View = useAppStore((state) => state.step3View)
  const setStep3View = useAppStore((state) => state.setStep3View)
  const days = useItineraryStore((state) => state.days)
  const activeDay = useItineraryStore((state) => state.activeDay)
  const day = days[activeDay]
  const destination = useTripConfigStore((s) => s.config.destination)

  // ── Full-screen map mode ──────────────────────────────────────────
  if (step3View === 'map-full') {
    return (
      <div className="relative flex h-full flex-col overflow-hidden bg-[var(--_bg)]">
        {/* Toolbar */}
        <div className="flex shrink-0 items-center justify-between border-b border-[var(--_border)] bg-[var(--_card)] px-4 py-2">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold text-[var(--_fg)]">🗺 Full Map View</span>
            {day && (
              <span className="text-xs text-[var(--_muted-fg)]">
                Day {day.day_number} · {day.items.length} stops
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* Day tabs */}
            <div className="flex gap-1 overflow-x-auto">
              {days.map((d, i) => (
                <button
                  key={d.day_number}
                  onClick={() => useItineraryStore.getState().setActiveDay(i)}
                  className={[
                    'shrink-0 rounded-lg px-3 py-1 text-xs font-medium transition-colors',
                    i === activeDay
                      ? 'bg-[var(--_primary)] text-white'
                      : 'bg-[var(--_card)] text-[var(--_muted-fg)] hover:text-[var(--_fg)] border border-[var(--_border)]',
                  ].join(' ')}
                >
                  Day {d.day_number}
                </button>
              ))}
            </div>
            <button
              onClick={() => setStep3View('itinerary')}
              className="ml-2 rounded-lg border border-[var(--_border)] px-3 py-1.5 text-xs font-medium text-[var(--_fg)] transition-colors hover:bg-[var(--_muted)] hover:text-[var(--_fg)]"
            >
              ✕ Close map
            </button>
          </div>
        </div>
        {/* Full-height map */}
        <div className="flex-1 overflow-hidden">
          <MapWrapper />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full overflow-hidden bg-[var(--_bg)]">
      {/* Left sidebar — metrics */}
      <aside
        className="w-[25%] min-w-[280px] shrink-0 overflow-y-auto bg-[var(--_card)]"
        style={{ boxShadow: 'inset -1px 0 0 var(--_border)' }}
      >
        <Column1Metrics />
      </aside>

      {/* Center — itinerary / comparison */}
      <section className="flex flex-1 flex-col overflow-hidden bg-[var(--_bg)]">
        {/* Center top-bar: title + share */}
        <div className="flex shrink-0 items-center justify-between border-b border-[var(--_border)] px-6 py-2">
          <p className="text-xs font-semibold text-[var(--_muted-fg)]">
            {destination ? `${destination.city}, ${destination.country}` : 'Your Itinerary'} · {days.length} days
          </p>
          <ShareButton />
        </div>
        <div className="flex-1 overflow-hidden px-8 py-4">
          {step3View === 'comparison' ? (
            <ComparisonPanel onClose={() => setStep3View('itinerary')} />
          ) : (
            <ItineraryTimeline />
          )}
        </div>
      </section>

      {/* Right sidebar — map + tips */}
      <aside
        className="w-[25%] min-w-[280px] shrink-0 overflow-y-auto bg-[var(--_card)]"
        style={{ boxShadow: 'inset 1px 0 0 var(--_border)' }}
      >
        {/* Full-map toggle button */}
        <div className="flex items-center justify-between border-b border-[var(--_border)] px-4 py-2">
          <span className="text-xs font-semibold uppercase tracking-widest text-[var(--_muted-fg)]">Map</span>
          <button
            onClick={() => setStep3View('map-full')}
            className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-[var(--_primary)] transition-colors hover:bg-[var(--_primary)]/10"
            title="Expand full-screen map"
          >
            ⤢ Full screen
          </button>
        </div>
        <Column3Sidebar />
      </aside>
    </div>
  )
}
