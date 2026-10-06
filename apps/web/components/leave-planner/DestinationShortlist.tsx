import type { DestinationCandidate } from '@/types'

interface Props {
  destinations: DestinationCandidate[]
  selectedDestination: DestinationCandidate | null
  onSelectDestination: (destination: DestinationCandidate) => void
  onPlanThisTrip: (destination: DestinationCandidate) => void
}

/** Accessible/fallback list of the ranked destination candidates — same
 * selection state as the map's markers, kept in sync via `selectedDestination`
 * so clicking a card or a marker both highlight the same entry. */
export function DestinationShortlist({ destinations, selectedDestination, onSelectDestination, onPlanThisTrip }: Props) {
  if (destinations.length === 0) {
    return (
      <p className="rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-4 text-sm text-[var(--_muted-fg)]">
        No destinations matched your interests for this state/window yet.
      </p>
    )
  }

  return (
    <ul className="flex flex-col gap-2.5">
      {destinations.map((destination) => {
        const isSelected = destination.destination === selectedDestination?.destination
        return (
          <li
            key={destination.destination}
            className={[
              'cursor-pointer rounded-xl border p-4 transition-colors',
              isSelected
                ? 'border-[var(--_primary)] bg-[var(--_primary)]/5'
                : 'border-[var(--_border)] bg-[var(--_card)] hover:border-[var(--_primary)]',
            ].join(' ')}
            onClick={() => onSelectDestination(destination)}
          >
            <p className="text-sm font-semibold text-[var(--_fg)]">{destination.destination}</p>
            <p className="mt-1 text-sm text-[var(--_muted-fg)]">{destination.rationale}</p>
            <p className="mt-1.5 text-xs font-medium text-[var(--_fg)]">{destination.workation_split}</p>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onPlanThisTrip(destination) }}
              className="btn btn-accent mt-3 rounded-lg px-4 py-2 text-xs font-bold"
            >
              Plan this trip
            </button>
          </li>
        )
      })}
    </ul>
  )
}
