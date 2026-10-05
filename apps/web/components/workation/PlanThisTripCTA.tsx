'use client'

import { ArrowRight } from 'lucide-react'
import { usePlanThisTrip } from '@/lib/workationHandoff'
import type { DestinationCandidate, LongWeekendSummary } from '@/types'

interface Props {
  destination: DestinationCandidate
  longWeekend: LongWeekendSummary | null
}

/** Given a selected destination + its matched long-weekend window, hands off
 * into the existing wizard/generation flow via `usePlanThisTrip` (shared
 * with the map popup's and shortlist card's inline "Plan this trip"
 * buttons — see lib/workationHandoff.ts for why this is one implementation,
 * not three). */
export function PlanThisTripCTA({ destination, longWeekend }: Props) {
  const planThisTrip = usePlanThisTrip()

  return (
    <button
      type="button"
      onClick={() => planThisTrip(destination, longWeekend)}
      className="btn btn-accent inline-flex items-center gap-2 rounded-2xl px-6 py-3.5 text-sm font-bold shadow-lg"
    >
      Plan this trip <ArrowRight size={18} />
    </button>
  )
}
