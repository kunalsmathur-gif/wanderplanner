import type { LongWeekendWindow } from '@/types'

interface Props {
  windows: LongWeekendWindow[]
}

/** Accessible/fallback list representation of the long-weekend windows — the
 * map (WorkationMapWrapper) is the primary visual/selection surface per the
 * plan's addendum, this is the same data in card form. */
export function LongWeekendList({ windows }: Props) {
  if (windows.length === 0) {
    return (
      <p className="rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-4 text-sm text-[var(--_muted-fg)]">
        No upcoming long weekends found for this state.
      </p>
    )
  }

  return (
    <ul className="flex flex-col gap-2.5">
      {windows.map((w) => (
        <li
          key={`${w.start_date}-${w.end_date}`}
          className="rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-4"
        >
          <p className="text-sm font-semibold text-[var(--_fg)]">
            {w.start_date} – {w.end_date}
          </p>
          <p className="mt-1 text-sm text-[var(--_muted-fg)]">{w.reason}</p>
          <p className="mt-1.5 text-xs font-medium text-[var(--_primary)]">
            {w.total_days_off} days off · {w.leave_days_needed} leave day{w.leave_days_needed === 1 ? '' : 's'} needed
          </p>
        </li>
      ))}
    </ul>
  )
}
