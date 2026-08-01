'use client'

import { LLMWizard } from '@/components/wizard/LLMWizard'
import { LandingHero } from '@/components/common/LandingHero'
import { useAppStore } from '@/store/appStore'

/**
 * The landing page, and only the landing page. A generated itinerary now
 * lives at `/itinerary` — this route used to render both off
 * `days.length > 0`, which is why the URL never changed between them.
 */
export default function Home() {
  const wizardOpen = useAppStore((state) => state.wizardOpen)

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Main content — blurred/dimmed while wizard is open */}
      <div
        className={wizardOpen
          ? 'pointer-events-none flex-1 select-none overflow-hidden opacity-40 blur-sm transition-all'
          : 'flex-1 overflow-hidden'}
        aria-hidden={wizardOpen}
      >
        <LandingHero />
      </div>

      {/* Wizard modal */}
      {wizardOpen && <LLMWizard />}
    </div>
  )
}
