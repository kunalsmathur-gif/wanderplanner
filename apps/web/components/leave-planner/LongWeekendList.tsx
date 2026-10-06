import type { LongWeekendWindow } from '@/types'

interface Props {
  windows: LongWeekendWindow[]
  // Optional selection mode: when `onSelect` is provided, each window
  // becomes a clickable control (Leave Planner's "pick one specific long
  // weekend" step) instead of a plain read-only card (the post-results
  // "here's what we searched" recap use).
  onSelect?: (window: LongWeekendWindow) => void
  selected?: LongWeekendWindow | null
}

/** Accessible/fallback list representation of the long-weekend windows — the
 * map (WorkationMapWrapper) is the primary visual/selection surface per the
 * plan's addendum, this is the same data in card form. */
export function LongWeekendList({ windows, onSelect, selected }: Props) {
  if (windows.length === 0) {
    return (
      <p className="rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-4 text-sm text-[var(--_muted-fg)]">
        No upcoming long weekends found for this state.
      </p>
    )
  }

  return (
    <ul className="flex flex-col gap-2.5" role={onSelect ? 'listbox' : undefined}>
      {windows.map((w) => {
        const isSelected = selected?.start_date === w.start_date && selected?.end_date === w.end_date
        const card = (
          <>
            <p className="text-sm font-semibold text-[var(--_fg)]">
              {w.start_date} – {w.end_date}
            </p>
            <p className="mt-1 text-sm text-[var(--_muted-fg)]">{w.reason}</p>
            <p className="mt-1.5 text-xs font-medium text-[var(--_primary)]">
              {w.total_days_off} days off · {w.leave_days_needed} leave day{w.leave_days_needed === 1 ? '' : 's'} needed
            </p>
          </>
        )

        return (
          <li key={`${w.start_date}-${w.end_date}`}>
            {onSelect ? (
              <button
                type="button"
                role="option"
                aria-selected={isSelected}
                onClick={() => onSelect(w)}
                className={[
                  'w-full rounded-xl border p-4 text-left transition-colors',
                  isSelected
                    ? 'border-[var(--_primary)] bg-[var(--_primary)]/10'
                    : 'border-[var(--_border)] bg-[var(--_card)] hover:border-[var(--_primary)]',
                ].join(' ')}
              >
                {card}
              </button>
            ) : (
              <div className="rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-4">
                {card}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
