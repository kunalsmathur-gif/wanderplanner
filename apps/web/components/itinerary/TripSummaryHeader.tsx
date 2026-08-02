'use client'

import dynamic from 'next/dynamic'
import { Edit2, MapPin, Wallet, CalendarDays } from 'lucide-react'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useAppStore } from '@/store/appStore'
import { useFeedbackPromptStore } from '@/store/feedbackPromptStore'
import { formatCurrency } from '@/lib/format'

const PdfDownloadButton = dynamic(
  () => import('@/components/pdf/PdfDownloadButton').then((m) => ({ default: m.PdfDownloadButton })),
  { ssr: false, loading: () => <div className="h-9 w-full animate-pulse rounded-lg bg-[var(--_muted)]" /> },
)

function MetricCell({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2.5 first:pl-3 last:pr-3">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[var(--_muted)] text-[var(--_primary)]">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[10px] font-medium text-[var(--_muted-fg)]">{label}</p>
        <p className="truncate text-xs font-semibold text-[var(--_fg)]">{value}</p>
      </div>
    </div>
  )
}

/**
 * Trip metrics + the two whole-trip actions (Edit Trip, Download PDF), shown
 * directly above the day-by-day breakdown.
 *
 * Moved out of the left/"Overview" panel in v10.56.0: on mobile these are the
 * first things a user looks for after generating a plan, and they were parked
 * behind a separate tab while that tab's own content (expenses, bookings) is
 * consulted far less often. They describe the itinerary, so they sit with it.
 */
export function TripSummaryHeader() {
  const budget = useTripConfigStore((state) => state.config.budget)
  const destination = useTripConfigStore((state) => state.config.destination)
  const destinationCountry = useTripConfigStore((state) => state.config.destination_country)
  const hops = useTripConfigStore((state) => state.config.hops)
  const days = useItineraryStore((state) => state.days)
  const openWizard = useAppStore((state) => state.openWizard)
  const requestFeedbackPrompt = useFeedbackPromptStore((state) => state.request)

  // "Edit Trip" is the closest real analog to "navigating back" in this UI
  // (there's no literal back button) — reopening the wizard means leaving
  // the current itinerary view, so it's the right moment to ask for a
  // reaction on the plan the user is about to move away from.
  function handleEditTrip() {
    if (days.length > 0) requestFeedbackPrompt('back')
    openWizard()
  }

  // Fallback chain so the metrics panel never shows a bare "—": prefer the
  // resolved city, then list multi-city stops, then fall back to the country
  // name for trips where the LLM hasn't resolved a concrete city yet.
  const destinationLabel = destination?.city
    ? hops.length > 0
      ? `${destination.city} +${hops.length}`
      : destination.city
    : (destinationCountry ?? '—')

  return (
    <section aria-label="Trip summary" className="space-y-3">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-[var(--_muted-fg)]">
        Trip Metrics
      </h3>

      <div className="flex items-stretch divide-x divide-[var(--_border)] overflow-hidden rounded-xl border border-[var(--_border)] bg-[var(--_card)]">
        <MetricCell icon={<MapPin size={14} />}       label="Destination" value={destinationLabel} />
        <MetricCell icon={<Wallet size={14} />}       label="Budget"      value={formatCurrency(budget.amount, budget.currency)} />
        <MetricCell icon={<CalendarDays size={14} />} label="Days"        value={String(days.length)} />
      </div>

      {/* Side by side from `sm` up so the pair costs one row, not two, on the
          narrow viewports where this header competes with the timeline. */}
      <div className="flex flex-col gap-2 sm:flex-row [&>*]:flex-1">
        {/* The label already names a job, which is more than the orb managed
            before — but it does not say that this is the *guided* route, and
            the orb reaches the same assistant a different way. The title spells
            out the difference at the point of choosing, so the user is not
            deciding between two identical-looking doors. */}
        <button
          onClick={handleEditTrip}
          type="button"
          className="btn btn-ghost w-full"
          title="Change destination, dates, budget or themes — Anya walks you through it step by step"
        >
          <Edit2 size={14} />
          Edit Trip
        </button>
        <PdfDownloadButton />
      </div>
    </section>
  )
}
