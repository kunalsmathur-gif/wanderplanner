'use client'

import { useMemo, useState } from 'react'

export interface WeekendRange {
  start: string
  end: string
}

interface Props {
  selected: WeekendRange | null
  onSelect: (range: WeekendRange) => void
}

const QUICK_PICK_COUNT = 6

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function formatLabel(start: Date, end: Date): string {
  const fmt = (d: Date) => d.toLocaleDateString('en-IN', { weekday: 'short', month: 'short', day: 'numeric' })
  return `${fmt(start)} – ${fmt(end)}`
}

/** Pure client-side "next N upcoming Saturday-Sundays" — no backend call
 * needed, this is just calendar math, unlike the state-anchored mode's
 * gazetted-holiday long weekends. Rolls forward to the *next* Saturday even
 * if today already is one, matching the same "upcoming, not already
 * underway" convention `_infer_weekend_dates_from_free_text` uses in the
 * wizard chat chain for "any weekend" phrasing. */
function nextWeekends(count: number): WeekendRange[] {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const cursor = new Date(today)
  const diffToSat = (6 - cursor.getDay() + 7) % 7
  cursor.setDate(cursor.getDate() + diffToSat)

  const options: WeekendRange[] = []
  for (let i = 0; i < count; i++) {
    const start = new Date(cursor)
    const end = new Date(cursor)
    end.setDate(end.getDate() + 1)
    options.push({ start: toISODate(start), end: toISODate(end) })
    cursor.setDate(cursor.getDate() + 7)
  }
  return options
}

/** Weekend picker for the Leave Planner's "just browse events across India"
 * mode — no home state, no gazetted holiday calendar, just the dates the
 * traveller already has in mind. Offers quick-pick chips for the next few
 * upcoming weekends plus a custom date range fallback for any other window
 * (a specific long weekend, a short trip spanning more than Sat-Sun, etc). */
export function WeekendQuickPicker({ selected, onSelect }: Props) {
  const quickPicks = useMemo(() => nextWeekends(QUICK_PICK_COUNT), [])
  const [customMode, setCustomMode] = useState(false)
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')

  function applyCustomRange() {
    if (!customStart || !customEnd) return
    onSelect({ start: customStart, end: customEnd })
  }

  return (
    <div>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Upcoming weekends">
        {quickPicks.map((range) => {
          const isSelected = !customMode && selected?.start === range.start && selected?.end === range.end
          return (
            <button
              key={range.start}
              type="button"
              onClick={() => {
                setCustomMode(false)
                onSelect(range)
              }}
              aria-pressed={isSelected}
              className={[
                'rounded-full border border-[var(--_primary)] px-3.5 py-2 text-xs font-medium transition-colors',
                isSelected
                  ? 'bg-[var(--_primary)] text-white'
                  : 'text-[var(--_primary)] hover:bg-[var(--_primary)] hover:text-white',
              ].join(' ')}
            >
              {formatLabel(new Date(range.start), new Date(range.end))}
            </button>
          )
        })}
        <button
          type="button"
          onClick={() => setCustomMode(true)}
          aria-pressed={customMode}
          className={[
            'rounded-full border border-dashed border-[var(--_border)] px-3.5 py-2 text-xs font-medium transition-colors',
            customMode
              ? 'border-[var(--_primary)] text-[var(--_primary)]'
              : 'text-[var(--_muted-fg)] hover:border-[var(--_primary)] hover:text-[var(--_primary)]',
          ].join(' ')}
        >
          Custom dates…
        </button>
      </div>

      {customMode && (
        <div className="mt-3 flex flex-wrap items-end gap-2.5">
          <label className="flex flex-col text-xs font-medium text-[var(--_muted-fg)]">
            From
            <input
              type="date"
              value={customStart}
              onChange={(e) => setCustomStart(e.target.value)}
              className="input mt-1 rounded-lg border border-[var(--_border)] bg-[var(--_card)] px-2.5 py-1.5 text-sm text-[var(--_fg)]"
            />
          </label>
          <label className="flex flex-col text-xs font-medium text-[var(--_muted-fg)]">
            To
            <input
              type="date"
              value={customEnd}
              onChange={(e) => setCustomEnd(e.target.value)}
              className="input mt-1 rounded-lg border border-[var(--_border)] bg-[var(--_card)] px-2.5 py-1.5 text-sm text-[var(--_fg)]"
            />
          </label>
          <button
            type="button"
            onClick={applyCustomRange}
            disabled={!customStart || !customEnd}
            className="btn rounded-lg border border-[var(--_primary)] px-3 py-1.5 text-xs font-semibold text-[var(--_primary)] disabled:opacity-50"
          >
            Use these dates
          </button>
        </div>
      )}
    </div>
  )
}
