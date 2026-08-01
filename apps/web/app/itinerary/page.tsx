'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { ThreeColumnLayout } from '@/components/layout/ThreeColumnLayout'
import { LLMWizard } from '@/components/wizard/LLMWizard'
import { FloatingAnyaButton } from '@/components/common/FloatingAnyaButton'
import { ChatPanel } from '@/components/chat/ChatPanel'
import { useAppStore } from '@/store/appStore'
import { useItineraryStore } from '@/store/itineraryStore'

/**
 * The generated trip, at its own URL.
 *
 * Previously this rendered inside `/` off `days.length > 0`, so the address
 * bar never changed between the landing page and a generated itinerary —
 * back/forward did nothing useful, the trip could not be linked to, and
 * logging out could not navigate away from it (`router.push('/')` was a no-op
 * on the page you were already on, which is why logout appeared to do
 * nothing).
 */
export default function ItineraryPage() {
  const router = useRouter()
  const wizardOpen = useAppStore((state) => state.wizardOpen)
  const days = useItineraryStore((state) => state.days)
  const hasHydrated = useItineraryStore.persist.hasHydrated()
  const hasItinerary = days.length > 0

  useEffect(() => {
    // Wait for the sessionStorage rehydration to finish before deciding the
    // page is empty — on the first client render `days` is always [], so
    // redirecting eagerly would bounce every refresh back to the landing page,
    // which is the exact failure this route was added to avoid.
    if (hasHydrated && !hasItinerary) {
      router.replace('/')
    }
  }, [hasHydrated, hasItinerary, router])

  if (!hasItinerary) {
    return (
      <div className="flex h-screen items-center justify-center" aria-live="polite">
        <span className="text-sm text-[var(--_muted-fg)]">
          {hasHydrated ? 'No itinerary yet — taking you back…' : 'Loading your itinerary…'}
        </span>
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <div
        className={wizardOpen
          ? 'pointer-events-none flex-1 select-none overflow-hidden opacity-40 blur-sm transition-all'
          : 'flex-1 overflow-hidden'}
        aria-hidden={wizardOpen}
      >
        <main id="main-content" aria-label="Wanderplanner itinerary dashboard" className="h-full">
          <ThreeColumnLayout />
        </main>
      </div>

      <FloatingAnyaButton />
      <ChatPanel />

      {wizardOpen && <LLMWizard />}
    </div>
  )
}
