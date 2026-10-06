import { Wifi, WifiOff } from 'lucide-react'
import type { DestinationCandidate } from '@/types'

interface Props {
  destination: DestinationCandidate
}

/** The 5-WFH-day/2-weekend-day split + wifi-verified venue counts for a
 * single selected destination — degrades honestly when venue coverage is
 * sparse (per the plan's "never fabricate coverage" note) rather than
 * padding the count. */
export function WorkationLogistics({ destination }: Props) {
  const { venue_summary: venues } = destination

  return (
    <div className="rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-4">
      <p className="text-sm font-semibold text-[var(--_fg)]">{destination.destination} — workation logistics</p>
      <p className="mt-1 text-sm text-[var(--_muted-fg)]">{destination.workation_split}</p>

      <div className="mt-3 flex items-center gap-2 text-sm">
        {venues.has_limited_coverage ? (
          <WifiOff size={16} className="shrink-0 text-amber-500" />
        ) : (
          <Wifi size={16} className="shrink-0 text-[var(--_primary)]" />
        )}
        <span className="text-[var(--_fg)]">
          {venues.venues_with_verified_wifi_count} of {venues.total_venues_found} venues have verified wifi
        </span>
      </div>
      {venues.has_limited_coverage && (
        <p className="mt-1 text-xs text-[var(--_muted-fg)]">
          Wifi tagging is limited for this destination — treat this as a starting point, not a complete list.
        </p>
      )}
    </div>
  )
}
