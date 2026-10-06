'use client'

import { LEAVE_PLANNER_INTERESTS } from './interests'

interface Props {
  selected: Set<string>
  onToggle: (interest: string) => void
}

/** Interest chip multi-select, shared by both Leave Planner discovery modes
 * (state/long-weekend anchored, and the stateless "browse events for a
 * weekend" mode) so the chip vocabulary and interaction never drift between
 * them — see `LEAVE_PLANNER_INTERESTS` for the shared vocabulary. */
export function InterestPicker({ selected, onToggle }: Props) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Interests">
      {LEAVE_PLANNER_INTERESTS.map((interest) => {
        const isSelected = selected.has(interest)
        return (
          <button
            key={interest}
            type="button"
            onClick={() => onToggle(interest)}
            aria-pressed={isSelected}
            className={[
              'rounded-full border border-[var(--_primary)] px-3.5 py-2 text-xs font-medium transition-colors',
              isSelected
                ? 'bg-[var(--_primary)] text-white'
                : 'text-[var(--_primary)] hover:bg-[var(--_primary)] hover:text-white',
            ].join(' ')}
          >
            {interest}
          </button>
        )
      })}
    </div>
  )
}
