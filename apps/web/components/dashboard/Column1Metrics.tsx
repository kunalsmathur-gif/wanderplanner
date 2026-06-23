'use client'

import dynamic from 'next/dynamic'
import { Edit2, BarChart2, MapPin, Wallet, CalendarDays, Target, Wifi } from 'lucide-react'
import { BookingLinksSection } from '@/components/itinerary/BookingLinksSection'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useAppStore } from '@/store/appStore'
import { CurrencyWidget } from '@/components/dashboard/CurrencyWidget'
import { ExpenseBreakupCard } from '@/components/dashboard/ExpenseBreakupCard'

const PdfDownloadButton = dynamic(
  () => import('@/components/pdf/PdfDownloadButton').then((m) => ({ default: m.PdfDownloadButton })),
  { ssr: false, loading: () => <div className="h-9 w-full animate-pulse rounded-lg bg-[var(--_muted)]" /> },
)

function MetricRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3 border-b border-[var(--_border)] py-2.5 last:border-0">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[var(--_muted)] text-[var(--_primary)]">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-[var(--_muted-fg)]">{label}</p>
        <p className="truncate text-sm font-semibold text-[var(--_fg)]">{value}</p>
      </div>
    </div>
  )
}

export function Column1Metrics() {
  const budget = useTripConfigStore((state) => state.config.budget)
  const destination = useTripConfigStore((state) => state.config.destination)
  const days = useItineraryStore((state) => state.days)
  const step3View = useAppStore((state) => state.step3View)
  const setStep3View = useAppStore((state) => state.setStep3View)
  const openWizard = useAppStore((state) => state.openWizard)

  const totalActivities = days.reduce((sum, day) => sum + day.items.length, 0)
  void totalActivities // used only for potential future re-add

  return (
    <div className="space-y-4 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-[var(--_muted-fg)]">
        Trip Metrics
      </h3>

      <div className="overflow-hidden rounded-xl border border-[var(--_border)] bg-[var(--_card)]">
        <MetricRow icon={<MapPin size={14} />}       label="Destination" value={destination?.city ?? '—'} />
        <MetricRow icon={<Wallet size={14} />}       label="Budget"      value={`${budget.currency} ${budget.amount.toLocaleString()}`} />
        <MetricRow icon={<CalendarDays size={14} />} label="Days"        value={String(days.length)} />
      </div>

      <div className="space-y-2 pt-1">
        <button onClick={openWizard} type="button" className="btn btn-ghost w-full">
          <Edit2 size={14} />
          Edit Trip
        </button>
        <button
          onClick={() => setStep3View(step3View === 'comparison' ? 'itinerary' : 'comparison')}
          type="button"
          className={step3View === 'comparison' ? 'btn btn-primary w-full' : 'btn btn-outline w-full'}
        >
          <BarChart2 size={14} />
          {step3View === 'comparison' ? 'Back to itinerary' : 'Compare destinations'}
        </button>
        <PdfDownloadButton />
      </div>

      {destination?.city && (
        <>
          <div className="border-t border-[var(--_border)] pt-3">
            <ExpenseBreakupCard />
          </div>
          <div className="border-t border-[var(--_border)] pt-3">
            <CurrencyWidget baseCurrency={budget.currency} />
          </div>
        </>
      )}
    </div>
  )
}
