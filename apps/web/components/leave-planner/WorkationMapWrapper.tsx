'use client'

import dynamic from 'next/dynamic'
import type { DestinationCandidate } from '@/types'

const WorkationMap = dynamic(() => import('./WorkationMap'), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center bg-slate-100 text-xs text-slate-400">
      Loading map…
    </div>
  ),
})

interface Props {
  destinations: DestinationCandidate[]
  selectedDestination: DestinationCandidate | null
  onSelectDestination: (destination: DestinationCandidate) => void
  onPlanThisTrip: (destination: DestinationCandidate) => void
}

export function WorkationMapWrapper(props: Props) {
  return (
    <div className="h-[360px] w-full overflow-hidden rounded-2xl border border-[var(--_border)] sm:h-[480px]">
      <WorkationMap {...props} />
    </div>
  )
}
