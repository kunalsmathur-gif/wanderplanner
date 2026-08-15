import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { getLastItinerary } from '@/lib/api'

/**
 * Loads the signed-in user's saved last itinerary (issue #65) into the
 * existing wizard/edit flow — the Account page's "continue your last trip"
 * card and Anya's "show me my last itinerary" chat intent both funnel
 * through this so the two entry points stay in lockstep with the same
 * store-population logic (`tripConfigStore` + `itineraryStore`), which is
 * all `/itinerary` needs to render the trip for continued re-editing.
 *
 * Returns the destination/dates summary on success (for a confirmation
 * message), or null if there is nothing to resume.
 */
export async function loadLastItinerary(): Promise<{ destination: string } | null> {
  const saved = await getLastItinerary()
  if (!saved) return null

  useTripConfigStore.getState().updateConfig(saved.trip_config)
  useItineraryStore.getState().setDays(
    saved.itinerary.days,
    saved.itinerary.alignment_score,
    saved.itinerary.expense_breakdown,
    saved.itinerary.generation_tier,
    saved.itinerary.warnings,
  )

  const destination = saved.trip_config.destination?.city || saved.trip_config.destination_country || 'your trip'
  return { destination }
}
