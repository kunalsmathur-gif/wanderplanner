'use client'

import { useEffect } from 'react'
import { useItineraryStore } from '@/store/itineraryStore'
import { sendGenerationSignal } from '@/lib/api'

/**
 * Reports the `session_duration` implicit-quality signal (issue #34) for
 * the itinerary currently on screen — see docs/rag-strategy.md's "Learning
 * Flywheel". Mount this once on the itinerary display route.
 *
 * The duration is measured from `generatedAt` (stamped in
 * `itineraryStore.setDays`, i.e. when this generation finished streaming)
 * to whichever of these happens first:
 *   - the tab is closed or the page is navigated away from entirely
 *     (`pagehide`/`beforeunload` — a React effect cleanup never runs then), or
 *   - `generationId` changes, e.g. an in-chat regeneration swaps in a new
 *     generation (the effect's cleanup fires for the *previous* id before
 *     the new run starts), or
 *   - this component unmounts (SPA navigation away from the route).
 *
 * Every path funnels through one `report()` so the signal is sent exactly
 * once per generation, however the session ends.
 */
export function useSessionDurationSignal() {
  const generationId = useItineraryStore((s) => s.generationId)
  const generatedAt = useItineraryStore((s) => s.generatedAt)

  useEffect(() => {
    if (!generationId || !generatedAt) return

    const report = () => {
      const elapsedSeconds = Math.max(0, Math.round((Date.now() - generatedAt) / 1000))
      sendGenerationSignal(generationId, 'session_duration', elapsedSeconds)
    }

    window.addEventListener('pagehide', report)
    window.addEventListener('beforeunload', report)
    return () => {
      window.removeEventListener('pagehide', report)
      window.removeEventListener('beforeunload', report)
      report()
    }
  }, [generationId, generatedAt])
}
