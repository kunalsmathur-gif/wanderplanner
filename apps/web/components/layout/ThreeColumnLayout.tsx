'use client'

import { useAppStore } from '@/store/appStore'
import { Column1Metrics } from '@/components/dashboard/Column1Metrics'
import { ItineraryTimeline } from '@/components/itinerary/ItineraryTimeline'
import { Column3Sidebar } from '@/components/itinerary/Column3Sidebar'
import { ComparisonPanel } from '@/components/comparison/ComparisonPanel'

export function ThreeColumnLayout() {
  const step3View = useAppStore((state) => state.step3View)
  const setStep3View = useAppStore((state) => state.setStep3View)

  return (
    <div className="flex h-full overflow-hidden bg-[#F7F4EF]">
      {/* Left sidebar - 25% - note card aesthetic */}
      <aside className="w-[25%] min-w-[280px] shrink-0 overflow-y-auto bg-white shadow-[inset_-1px_0_0_rgba(26,58,82,0.1)]">
        <Column1Metrics />
      </aside>

      {/* Center - 50% - breathing room for itinerary */}
      <section className="flex flex-1 flex-col overflow-hidden bg-[#F7F4EF] px-8 py-6">
        {step3View === 'comparison' ? (
          <ComparisonPanel onClose={() => setStep3View('itinerary')} />
        ) : (
          <ItineraryTimeline />
        )}
      </section>

      {/* Right sidebar - 25% - map + tips */}
      <aside className="w-[25%] min-w-[280px] shrink-0 overflow-y-auto bg-white shadow-[inset_1px_0_0_rgba(26,58,82,0.1)]">
        <Column3Sidebar />
      </aside>
    </div>
  )
}
