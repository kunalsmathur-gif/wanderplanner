'use client'

import dynamic from 'next/dynamic'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useAppStore } from '@/store/appStore'
import { CurrencyWidget } from '@/components/dashboard/CurrencyWidget'
import { ExpenseBreakupCard } from '@/components/dashboard/ExpenseBreakupCard'
import { BookingLinksSection } from '@/components/itinerary/BookingLinksSection'

const PdfDownloadButton = dynamic(
  () => import('@/components/pdf/PdfDownloadButton').then((m) => ({ default: m.PdfDownloadButton })),
  { ssr: false, loading: () => <div className="h-9 w-full animate-pulse rounded-lg bg-slate-100" /> },
)

export function Column1Metrics() {
  const budget = useTripConfigStore((state) => state.config.budget)
  const destination = useTripConfigStore((state) => state.config.destination)
  const days = useItineraryStore((state) => state.days)
  const step3View = useAppStore((state) => state.step3View)
  const setStep3View = useAppStore((state) => state.setStep3View)
  const openWizard = useAppStore((state) => state.openWizard)

  const totalActivities = days.reduce((sum, day) => sum + day.items.length, 0)

  return (
    <div className="space-y-4 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        🛄 Trip Metrics
      </h3>

      <div className="space-y-0">
        <MetricRow icon="📍" label="Destination" value={destination?.city ?? '—'} />
        <MetricRow icon="💶" label="Budget" value={`${budget.currency} ${budget.amount.toLocaleString()}`} />
        <MetricRow icon="🗓️" label="Days" value={String(days.length)} />
        <MetricRow icon="🎯" label="Activities" value={String(totalActivities)} />
        <MetricRow icon="🛂" label="Visa" value="Check embassy" />
        <MetricRow icon="📶" label="eSIM" value="See provider" />
      </div>

      <div className="space-y-2 pt-1">
        <button
          onClick={openWizard}
          className="h-9 w-full rounded-lg border border-slate-300 text-xs font-semibold text-slate-700 transition-all hover:bg-slate-100"
          type="button"
        >
          ✏️ Edit Trip
        </button>
        <button
          onClick={() => setStep3View(step3View === 'comparison' ? 'itinerary' : 'comparison')}
          className={[
            'h-9 w-full rounded-lg border text-xs font-semibold transition-all',
            step3View === 'comparison'
              ? 'border-[#1E40AF] bg-[#1E40AF] text-white'
              : 'border-[#1E40AF] text-[#1E40AF] hover:bg-blue-50',
          ].join(' ')}
          type="button"
        >
          {step3View === 'comparison' ? '← Back to itinerary' : '🗺️ Compare destinations'}
        </button>
        <PdfDownloadButton />
      </div>

      {destination?.city && (
        <>
          <div className="border-t border-slate-100 pt-2">
            <BookingLinksSection />
          </div>
          <div className="border-t border-slate-100 pt-2">
            <ExpenseBreakupCard />
          </div>
          <div className="border-t border-slate-100 pt-2">
            <CurrencyWidget baseCurrency={budget.currency} />
          </div>
        </>
      )}
    </div>
  )
}

function MetricRow({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 py-1.5 last:border-0">
      <span className="text-xs text-slate-500">{icon} {label}</span>
      <span className="ml-2 max-w-[110px] truncate text-xs font-medium text-[#0F172A]">{value}</span>
    </div>
  )
}
