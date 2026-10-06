import { useRouter } from 'next/navigation'
import { useAppStore } from '@/store/appStore'
import { savePendingGeneration } from '@/lib/pendingGeneration'
import { logClientEvent } from '@/lib/analyticsBeacon'
import type { DestinationCandidate, LongWeekendSummary, TripConfig } from '@/types'

function buildTripConfig(destination: DestinationCandidate, longWeekend: LongWeekendSummary | null): TripConfig {
  return {
    purpose: 'leisure',
    dates: {
      start: longWeekend?.start_date ?? null,
      end: longWeekend?.end_date ?? null,
      flexible: !longWeekend,
      duration_days: longWeekend ? undefined : 3,
    },
    scope: 'domestic',
    origin: { city: '', iata: '', lat: 0, lon: 0 },
    destination: {
      city: destination.destination,
      country: 'India',
      lat: destination.lat,
      lon: destination.lon,
    },
    destination_mode: 'fixed',
    destination_country: null,
    hops: [],
    fixed_stop_order: false,
    themes: [],
    personas: [],
    group: { infants: 0, kids: [], adults: 1, seniors: 0, pets: 0 },
    accommodation: {
      style: [],
      min_bedrooms: 1,
      bathrooms: 1,
      private_pool: false,
      kitchen: false,
      wheelchair_accessible: false,
      pet_friendly: false,
    },
    pace: 'moderate',
    crowd_preference: 'balanced',
    budget: { amount: 0, currency: 'INR' },
    splurge_categories: [],
    save_categories: [],
    prebooked_flights_inr: null,
    prebooked_accommodation_inr: null,
    pinned_pois: [],
    day_cost_preferences: [],
  }
}

/** Shared "hand off a chosen workation destination into the wizard" logic,
 * used both by the standalone `PlanThisTripCTA` button and by the map/
 * shortlist's inline "Plan this trip" actions — one implementation so the
 * handoff mechanics (build config, save pending generation, open wizard,
 * navigate) never drift between the two entry points. Mirrors the exact
 * pattern `ChatPanel.tsx` already uses to resume generation after a re-auth
 * round trip: `savePendingGeneration` + `useAppStore.getState().openWizard()`
 * + `router.push('/')`, which `LLMWizard`'s own mount effect
 * (`getPendingGeneration`/`hasResumedGenerationRef`) then picks up. */
export function usePlanThisTrip() {
  const router = useRouter()

  return function planThisTrip(destination: DestinationCandidate, longWeekend: LongWeekendSummary | null) {
    const tripConfig = buildTripConfig(destination, longWeekend)
    logClientEvent('leave_planner_handoff', {
      destination: destination.destination,
      start_date: longWeekend?.start_date ?? null,
      end_date: longWeekend?.end_date ?? null,
    })
    savePendingGeneration(tripConfig)
    useAppStore.getState().openWizard()
    router.push('/')
  }
}
