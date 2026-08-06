'use client'

import { LayoutList, Wallet, Map } from 'lucide-react'
import { useAppStore } from '@/store/appStore'
import type { MobileTab } from '@/store/appStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { BookingExpensesPanel } from '@/components/dashboard/BookingExpensesPanel'
import { TripSummaryHeader } from '@/components/itinerary/TripSummaryHeader'
import { ItineraryTimeline } from '@/components/itinerary/ItineraryTimeline'
import { Column3Sidebar } from '@/components/itinerary/Column3Sidebar'
import { ComparisonPanel } from '@/components/comparison/ComparisonPanel'
import { MapWrapper } from '@/components/map/MapWrapper'
import { ShareButton } from '@/components/common/ShareButton'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { UserMenu } from '@/components/common/UserMenu'
import { TripFeedbackPopup } from '@/components/itinerary/TripFeedbackPopup'

// ── Fallback-tier disclosure banner ───────────────────────────────────────────
// generation_tier !== 'live' means the backend degraded to cache / RAG
// skeleton / (enhanced) mock data (docs §4) — never present that as a fully
// verified, freshly-generated plan without saying so.
const TIER_COPY: Record<string, string> = {
  live_unverified: 'This plan is based on general AI knowledge — Wanderplanner has no verified local research for this destination yet, so details may be less accurate.',
  cache: 'Showing a previously generated plan for a similar trip — live generation was unavailable.',
  rag_skeleton: 'Built from verified places only, without AI narration — live generation was unavailable.',
  enhanced_mock: 'This is a backup sample plan with real destination tips spliced in — live generation failed.',
  mock: 'This is a sample plan for demo purposes, not a live generation.',
}

function GenerationTierBanner() {
  const tier = useItineraryStore((state) => state.generationTier)
  if (tier === 'live') return null
  const message = TIER_COPY[tier] ?? 'This plan uses backup data — some details may be less current.'
  return (
    <div
      role="status"
      className="flex shrink-0 items-center gap-2 border-b border-amber-300/60 bg-amber-50 px-4 py-1.5 text-xs font-medium text-amber-800 dark:border-amber-700/40 dark:bg-amber-950/30 dark:text-amber-400 sm:px-6"
    >
      <span aria-hidden="true">⚠️</span>
      <span>{message}</span>
    </div>
  )
}

// ── Shared title bar ──────────────────────────────────────────────────────────
function TitleBar({ destination, days }: { destination: { city: string; country: string } | null; days: number }) {
  return (
    <div className="flex shrink-0 flex-col">
      <div className="flex items-center justify-between border-b border-[var(--_border)] px-4 py-2 sm:px-6">
        <p className="truncate text-xs font-semibold text-[var(--_muted-fg)]">
          {destination ? `${destination.city}, ${destination.country}` : 'Your Itinerary'} · {days} days
        </p>
        <div className="flex items-center gap-2">
          <ThemeToggle className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--_border)] text-[var(--_fg)] transition-colors hover:border-[var(--_primary)] hover:text-[var(--_primary)]" />
          <ShareButton />
          <UserMenu />
        </div>
      </div>
      <GenerationTierBanner />
    </div>
  )
}

// ── Bottom tab bar (mobile only) ──────────────────────────────────────────────
function MobileTabBar({ active, onChange }: { active: MobileTab; onChange: (tab: MobileTab) => void }) {
  const tabs: { id: MobileTab; label: string; Icon: typeof LayoutList }[] = [
    { id: 'itinerary', label: 'Itinerary', Icon: LayoutList },
    // Two words at 10px in a third of a phone screen — kept short enough not
    // to wrap or truncate on a 320px viewport.
    { id: 'bookings', label: 'Booking & Expenses', Icon: Wallet },
    { id: 'map',      label: 'Maps & Tips', Icon: Map },
  ]
  return (
    <nav
      aria-label="Dashboard sections"
      // Frozen to the viewport bottom rather than sitting at the end of the
      // scroll flow. `z-30` keeps it under the Anya orb (z-40), the feedback
      // popup (z-50) and the chat panel (z-9998), all of which are meant to
      // sit over the whole page. The safe-area inset keeps the labels off the
      // home indicator on notched phones — the previous `pb-safe` spacer was a
      // no-op, since no such utility is defined in globals.css or the theme.
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-[var(--_border)] bg-[var(--_card)] pb-[env(safe-area-inset-bottom)] lg:hidden"
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
  const mobileTab = useAppStore((state) => state.mobileTab)
  const setMobileTab = useAppStore((state) => state.setMobileTab)
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
        <div className="flex shrink-0 flex-col gap-2 border-b border-[var(--_border)] bg-[var(--_card)] px-4 py-2">
          <div className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-3">
              <span className="whitespace-nowrap text-sm font-semibold text-[var(--_fg)]">🗺 Full Map View</span>
              {day && (
                <span className="hidden truncate text-xs text-[var(--_muted-fg)] sm:inline">
                  Day {day.day_number} · {day.items.length} stops
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={() => setStep3View('itinerary')}
              className="shrink-0 rounded-lg border border-[var(--_border)] px-3 py-1.5 text-xs font-medium text-[var(--_fg)] transition-colors hover:bg-[var(--_muted)]"
            >
              ✕ Close
            </button>
          </div>
          {/* Day tabs — scrollable on mobile, own row so they never push Close off-screen */}
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

      {/* Reserves everything floating over this container, since neither the
          frozen tab bar nor the Anya orb takes space in the scroll flow:

            • tab bar ~51px (18px icon + 4px gap + 12px label + 16px padding
              + 1px border), flush to the bottom;
            • the orb sits on top of it at `bottom-[3.5rem + safe-area]` and
              is 44px tall on mobile, so its top edge is ~100px up.

          7rem (112px) clears both with slack. ⚠️ The orb returned to mobile in
          v10.60 at a smaller size after being pulled in v10.58, and this is
          the number that has to move with it — when the reservation and the
          orb disagree, the orb sits *on* the last card's CTA and wins the tap
          (it covered "Get Quotation" exactly that way before v10.56.1). */}
      <div className="flex-1 overflow-y-auto pb-[calc(7rem+env(safe-area-inset-bottom))]">
        {mobileTab === 'itinerary' && (
          <div className="space-y-4 px-4 py-4">
            {step3View === 'comparison' ? (
              <ComparisonPanel onClose={() => setStep3View('itinerary')} />
            ) : (
              <>
                <TripSummaryHeader />
                <ItineraryTimeline />
              </>
            )}
          </div>
        )}
        {mobileTab === 'bookings' && <BookingExpensesPanel />}
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
        aria-label="Booking and expenses"
      >
        <BookingExpensesPanel />
      </aside>

      {/* Center — itinerary / comparison. Desktop mirrors the mobile grouping
          on purpose: the same three sections in the same order, so the two
          layouts stay one information architecture rather than two. */}
      <section className="flex flex-1 flex-col overflow-hidden bg-[var(--_bg)]">
        <TitleBar destination={destination} days={days.length} />
        <div className="flex-1 overflow-y-auto px-8 py-4">
          {step3View === 'comparison' ? (
            <ComparisonPanel onClose={() => setStep3View('itinerary')} />
          ) : (
            <div className="space-y-4">
              <TripSummaryHeader />
              <ItineraryTimeline />
            </div>
          )}
        </div>
      </section>

      {/* Right sidebar — map + tips. Same orb reservation as mobile: on desktop
          it moves to `lg:bottom-6`, and `right-6` puts it over *this* column,
          so its content needs the clearance rather than the centre one. */}
      <aside
        className="w-[25%] min-w-[280px] shrink-0 overflow-y-auto bg-[var(--_card)] pb-32"
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
      <TripFeedbackPopup />
    </>
  )
}
