'use client'

import { ThreeColumnLayout } from '@/components/layout/ThreeColumnLayout'
import { LLMWizard } from '@/components/wizard/LLMWizard'
import { FloatingAnyaButton } from '@/components/common/FloatingAnyaButton'
import { LandingHero } from '@/components/common/LandingHero'
import { ChatPanel } from '@/components/chat/ChatPanel'
import { useAppStore } from '@/store/appStore'
import { useItineraryStore } from '@/store/itineraryStore'

export default function Home() {
  const wizardOpen = useAppStore((state) => state.wizardOpen)
  const days = useItineraryStore((state) => state.days)
  const hasItinerary = days.length > 0

  // Content behind any wizard overlay
  const content = hasItinerary ? <ThreeColumnLayout /> : <LandingHero />

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Main content — blurred/dimmed while wizard is open */}
      <div
        className={wizardOpen
          ? 'pointer-events-none flex-1 select-none overflow-hidden opacity-40 blur-sm transition-all'
          : 'flex-1 overflow-hidden'}
        aria-hidden={wizardOpen}
      >
        {hasItinerary
          ? (
          <main id="main-content" aria-label="Wanderplanner itinerary dashboard" className="h-full">
              <ThreeColumnLayout />
            </main>
          )
          : content}
      </div>

      {/* Anya orb — only shown when itinerary exists and wizard is closed */}
      {hasItinerary && <FloatingAnyaButton />}

      {/* Anya persistent chat panel */}
      {hasItinerary && <ChatPanel />}

      {/* Wizard modal */}
      {wizardOpen && <LLMWizard />}
    </div>
  )
}

