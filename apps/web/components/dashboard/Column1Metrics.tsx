'use client'

import dynamic from 'next/dynamic'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useAppStore } from '@/store/appStore'
import { BestTimeWidget } from '@/components/dashboard/BestTimeWidget'
import { CurrencyWidget } from '@/components/dashboard/CurrencyWidget'

const PdfDownloadButton = dynamic(
  () => import('@/components/pdf/PdfDownloadButton').then((m) => ({ default: m.PdfDownloadButton })),
  { ssr: false, loading: () => <div className="w-full h-9 bg-slate-100 rounded-lg animate-pulse" /> },
)

export function Column1Metrics() {
  const budget = useTripConfigStore((s) => s.config.budget)
  const destination = useTripConfigStore((s) => s.config.destination)
  const days = useItineraryStore((s) => s.days)
  const { step3View, setStep3View } = useAppStore()

  const totalActivities = days.reduce((sum, d) => sum + d.items.length, 0)

  return (
    <div className="p-4 space-y-4">
      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
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

      <div className="pt-1 space-y-2">
        <button
          onClick={() => setStep3View(step3View === 'comparison' ? 'itinerary' : 'comparison')}
          className={[
            'w-full h-9 rounded-lg text-xs font-semibold border transition-all',
            step3View === 'comparison'
              ? 'bg-[#1E40AF] text-white border-[#1E40AF]'
              : 'border-[#1E40AF] text-[#1E40AF] hover:bg-blue-50',
          ].join(' ')}
        >
          {step3View === 'comparison' ? '← Back to itinerary' : '🗺️ Compare destinations'}
        </button>
        <PdfDownloadButton />
      </div>

      {destination?.city && (
        <>
          <div className="border-t border-slate-100 pt-2">
            <BestTimeWidget destination={destination.city} />
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
    <div className="flex items-center justify-between py-1.5 border-b border-slate-100 last:border-0">
      <span className="text-xs text-slate-500">{icon} {label}</span>
      <span className="text-xs font-medium text-[#0F172A] truncate ml-2 max-w-[110px]">{value}</span>
    </div>
  )
}
