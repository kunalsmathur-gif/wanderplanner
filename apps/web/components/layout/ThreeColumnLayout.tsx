'use client'

import { useAppStore } from '@/store/appStore'
import { Column1Metrics } from '@/components/dashboard/Column1Metrics'
import { ItineraryTimeline } from '@/components/itinerary/ItineraryTimeline'
import { Column3Sidebar } from '@/components/itinerary/Column3Sidebar'
import { ComparisonPanel } from '@/components/comparison/ComparisonPanel'

export function ThreeColumnLayout() {
  const { step3View, setStep3View, goBack } = useAppStore()

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Top bar with back button */}
      <div className="flex items-center px-4 py-2 border-b border-slate-200 bg-white shrink-0">
        <button
          onClick={goBack}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-[#1E40AF] transition-colors"
        >
          ← Back to Overview
        </button>
      </div>

      {/* Three-column body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Column 1 — 20% — Trip metrics & utilities */}
        <aside className="w-[20%] min-w-[220px] border-r border-slate-200 overflow-y-auto bg-slate-50 shrink-0">
          <Column1Metrics />
        </aside>

        {/* Column 2 — 55% — Timeline or Comparison */}
        <section className="flex-1 overflow-hidden flex flex-col">
          {step3View === 'comparison' ? (
            <ComparisonPanel onClose={() => setStep3View('itinerary')} />
          ) : (
            <ItineraryTimeline />
          )}
        </section>

        {/* Column 3 — 25% — Social media & embeds */}
        <aside className="w-[25%] min-w-[260px] border-l border-slate-200 overflow-y-auto bg-slate-50 shrink-0">
          <Column3Sidebar />
        </aside>
      </div>
    </div>
  )
}
