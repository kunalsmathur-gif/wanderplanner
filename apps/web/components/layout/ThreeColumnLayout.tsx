'use client'

import { useState } from 'react'
import { LayoutList, BarChart2, Map } from 'lucide-react'
import { useAppStore } from '@/store/appStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { Column1Metrics } from '@/components/dashboard/Column1Metrics'
import { ItineraryTimeline } from '@/components/itinerary/ItineraryTimeline'
import { Column3Sidebar } from '@/components/itinerary/Column3Sidebar'
import { ComparisonPanel } from '@/components/comparison/ComparisonPanel'
import { MapWrapper } from '@/components/map/MapWrapper'
import { ShareButton } from '@/components/common/ShareButton'

type MobileTab = 'itinerary' | 'overview' | 'map'

// ── Shared title bar ──────────────────────────────────────────────────────────
function TitleBar({ destination, days }: { destination: { city: string; country: string } | null; days: number }) {
  return (
    <div className="flex shrink-0 items-center justify-between border-b border-[var(--_border)] px-4 py-2 sm:px-6">
      <p className="truncate text-xs font-semibold text-[var(--_muted-fg)]">
        {destination ? `${destination.city}, ${destination.country}` : 'Your Itinerary'} · {days} days
      </p>
      <ShareButton />
    </div>
  )
}

// ── Bottom tab bar (mobile only) ──────────────────────────────────────────────
function MobileTabBar({ active, onChange }: { active: MobileTab; onChange: (tab: MobileTab) => void }) {
  const tabs: { id: MobileTab; label: string; Icon: typeof LayoutList }[] = [
    { id: 'itinerary', label: 'Itinerary', Icon: LayoutList },
    { id: 'overview', label: 'Overview',  Icon: BarChart2 },
    { id: 'map',      label: 'Map & Tips', Icon: Map },
  ]
  return (
    <nav
      aria-label="Dashboard sections"
      className="flex shrink-0 border-t border-[var(--_border)] bg-[var(--_card)]"
    >
      {tabs.map(({ id, label, Icon }) => (
        <button
          key={id}
          type="button"
          onClick={() => onChange(id)}
          aria-current={active === id ? 'page' : undefined}
          className={[
            'flex flex-1 flex-col items-center gap-1 py-2 text-[10px] font-semibold transition-colors',
            active === id
              ? 'text-[var(--_primary)]'
              : 'text-[var(--_muted-fg)] hover:text-[var(--_fg)]',
          ].join(' ')}
        >
          <Icon size={18} aria-hidden="true" />
          {label}
        </button>
      ))}
    </nav>
  )
}

export function ThreeColumnLayout() {
  const [mobileTab, setMobileTab] = useState<MobileTab>('itinerary')
  const step3View = useAppStore((state) => state.step3View)
  const setStep3View = useAppStore((state) => state.setStep3View)
  const days = useItineraryStore((state) => state.days)
  const activeDay = useItineraryStore((state) => state.activeDay)
  const day = days[activeDay]
  const destination = useTripConfigStore((s) => s.config.destination)

  // ── Full-screen map mode ──────────────────────────────────────────────────
  if (step3View === 'map-full') {
    return (
      <div className="relative flex h-full flex-col overflow-hidden bg-[var(--_bg)]">
        {/* Toolbar */}
        <div className="flex shrink-0 items-center justify-between border-b border-[var(--_border)] bg-[var(--_card)] px-4 py-2">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold text-[var(--_fg)]">🗺 Full Map View</span>
            {day && (
              <span className="hidden text-xs text-[var(--_muted-fg)] sm:inline">
                Day {day.day_number} · {day.items.length} stops
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* Day tabs — scrollable on mobile */}
            <div className="flex gap-1 overflow-x-auto">
              {days.map((d, i) => (
                <button
                  key={d.day_number}
                  type="button"
                  onClick={() => useItineraryStore.getState().setActiveDay(i)}
                  className={[
                    'shrink-0 rounded-lg px-3 py-1 text-xs font-medium transition-colors',
                    i === activeDay
                      ? 'bg-[var(--_primary)] text-white'
                      : 'border border-[var(--_border)] bg-[var(--_card)] text-[var(--_muted-fg)] hover:text-[var(--_fg)]',
                  ].join(' ')}
                >
                  Day {d.day_number}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setStep3View('itinerary')}
              className="ml-2 rounded-lg border border-[var(--_border)] px-3 py-1.5 text-xs font-medium text-[var(--_fg)] transition-colors hover:bg-[var(--_muted)]"
            >
              ✕ Close
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

  // ── Mobile layout (< lg): single panel + bottom tabs ─────────────────────
  const mobileContent = (
    <div className="flex h-full flex-col overflow-hidden bg-[var(--_bg)] lg:hidden">
      <TitleBar destination={destination} days={days.length} />

      <div className="flex-1 overflow-y-auto">
        {mobileTab === 'itinerary' && (
          <div className="px-4 py-4">
            {step3View === 'comparison' ? (
              <ComparisonPanel onClose={() => setStep3View('itinerary')} />
            ) : (
              <ItineraryTimeline />
            )}
          </div>
        )}
        {mobileTab === 'overview' && <Column1Metrics />}
        {mobileTab === 'map' && (
          <div>
            {/* Compact inline map */}
            <div className="flex items-center justify-between border-b border-[var(--_border)] px-4 py-2">
              <span className="text-xs font-semibold uppercase tracking-widest text-[var(--_muted-fg)]">Map</span>
              <button
                type="button"
                onClick={() => setStep3View('map-full')}
                className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-[var(--_primary)] transition-colors hover:bg-[var(--_primary)]/10"
              >
                ⤢ Full screen
              </button>
            </div>
            <Column3Sidebar />
          </div>
        )}
      </div>

      {/* Extra bottom padding so content isn't hidden behind the tab bar */}
      <div className="shrink-0 pb-safe" aria-hidden="true" />

      <MobileTabBar active={mobileTab} onChange={setMobileTab} />
    </div>
  )

  // ── Desktop layout (≥ lg): three columns ─────────────────────────────────
  const desktopContent = (
    <div className="hidden h-full overflow-hidden bg-[var(--_bg)] lg:flex">
      {/* Left sidebar — metrics */}
      <aside
        className="w-[25%] min-w-[280px] shrink-0 overflow-y-auto bg-[var(--_card)]"
        style={{ boxShadow: 'inset -1px 0 0 var(--_border)' }}
      >
        <Column1Metrics />
      </aside>

      {/* Center — itinerary / comparison */}
      <section className="flex flex-1 flex-col overflow-hidden bg-[var(--_bg)]">
        <TitleBar destination={destination} days={days.length} />
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
        <div className="flex items-center justify-between border-b border-[var(--_border)] px-4 py-2">
          <span className="text-xs font-semibold uppercase tracking-widest text-[var(--_muted-fg)]">Map</span>
          <button
            type="button"
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

  return (
    <>
      {mobileContent}
      {desktopContent}
    </>
  )
}
