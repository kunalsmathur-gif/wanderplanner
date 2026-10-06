'use client'

import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { getLongWeekends, getWorkationRecommendations } from '@/lib/api'
import { InterestPicker } from './InterestPicker'
import { LongWeekendList } from './LongWeekendList'
import { WeekendQuickPicker, type WeekendRange } from './WeekendQuickPicker'
import type { LongWeekendWindow, WorkationRecommendResponse } from '@/types'

// Indian states + UTs, hardcoded per the plan ("India-specific, no paid
// holiday API") — state-wise gazetted holiday coverage lives server-side in
// `apps/api/services/data/`, this list is just the dropdown vocabulary.
const INDIAN_STATES = [
  'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Goa',
  'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand', 'Karnataka', 'Kerala',
  'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland',
  'Odisha', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
  'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
  'Andaman and Nicobar Islands', 'Chandigarh',
  'Dadra and Nagar Haveli and Daman and Diu', 'Delhi', 'Jammu and Kashmir',
  'Ladakh', 'Lakshadweep', 'Puducherry',
] as const

type Mode = 'state' | 'browse'

interface Props {
  onResults: (recommendations: WorkationRecommendResponse) => void
  onError: (message: string) => void
}

/**
 * Two-step, two-mode Leave Planner discovery flow (redesigned 2026-10-06,
 * replacing the single-step "state + interests" form):
 *
 * - **Mode 'state'** ("plan around my long weekends"): pick a home state ->
 *   pick ONE specific upcoming long weekend from that state's gazetted
 *   holiday calendar -> pick interests -> see matching events/destinations
 *   for that specific window. Interests now come *after* the weekend is
 *   chosen, not alongside it, so the user commits to "when" before "what."
 * - **Mode 'browse'** ("just show me events for a weekend"): no home state
 *   at all — pick any weekend/date range (quick-pick chips or custom dates)
 *   -> optionally narrow by interests -> see events happening across India
 *   for those exact dates, with no long-weekend/leave-day reasoning at all.
 *
 * Both modes funnel into the same `getWorkationRecommendations` call and the
 * same map/shortlist results UI in `app/leave-planner/page.tsx` — only how
 * the destination's search window and `state` are decided differs.
 */
export function LeavePlannerFlow({ onResults, onError }: Props) {
  const [mode, setMode] = useState<Mode>('state')

  // Mode 'state' step 1: home state -> that state's long-weekend windows.
  const [state, setState] = useState('')
  const [longWeekends, setLongWeekends] = useState<LongWeekendWindow[]>([])
  const [loadingWindows, setLoadingWindows] = useState(false)
  const [windowsError, setWindowsError] = useState<string | null>(null)
  const [selectedWindow, setSelectedWindow] = useState<LongWeekendWindow | null>(null)

  // Mode 'browse' step 1: an explicit weekend/date range, no state involved.
  const [selectedWeekend, setSelectedWeekend] = useState<WeekendRange | null>(null)

  // Step 2 (both modes): interests, then submit.
  const [interests, setInterests] = useState<Set<string>>(new Set())
  const [submitting, setSubmitting] = useState(false)

  function resetSelection() {
    setState('')
    setLongWeekends([])
    setSelectedWindow(null)
    setSelectedWeekend(null)
    setInterests(new Set())
    setWindowsError(null)
  }

  function handleModeChange(next: Mode) {
    if (next === mode) return
    setMode(next)
    resetSelection()
  }

  async function handleStateChange(nextState: string) {
    setState(nextState)
    setSelectedWindow(null)
    setLongWeekends([])
    setWindowsError(null)
    if (!nextState) return
    setLoadingWindows(true)
    try {
      const windows = await getLongWeekends(nextState)
      setLongWeekends(windows)
    } catch {
      setWindowsError("Couldn't load long weekends for this state right now — please try again in a moment.")
    } finally {
      setLoadingWindows(false)
    }
  }

  function toggleInterest(interest: string) {
    setInterests((prev) => {
      const next = new Set(prev)
      if (next.has(interest)) next.delete(interest)
      else next.add(interest)
      return next
    })
  }

  const dateRange: [string, string] | null =
    mode === 'state' && selectedWindow
      ? [selectedWindow.start_date, selectedWindow.end_date]
      : mode === 'browse' && selectedWeekend
        ? [selectedWeekend.start, selectedWeekend.end]
        : null

  async function handleSubmit() {
    if (!dateRange || submitting) return
    setSubmitting(true)
    try {
      const recommendations = await getWorkationRecommendations(
        mode === 'state' ? state : null,
        Array.from(interests),
        dateRange,
      )
      onResults(recommendations)
    } catch {
      onError("Couldn't load events for these dates right now — please try again in a moment.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-5 sm:p-6">
      <div className="mb-5 flex gap-1.5 rounded-xl border border-[var(--_border)] p-1" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'state'}
          onClick={() => handleModeChange('state')}
          className={[
            'flex-1 rounded-lg px-3 py-2 text-xs font-semibold transition-colors',
            mode === 'state' ? 'bg-[var(--_primary)] text-white' : 'text-[var(--_muted-fg)] hover:text-[var(--_fg)]',
          ].join(' ')}
        >
          Plan around my long weekends
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'browse'}
          onClick={() => handleModeChange('browse')}
          className={[
            'flex-1 rounded-lg px-3 py-2 text-xs font-semibold transition-colors',
            mode === 'browse' ? 'bg-[var(--_primary)] text-white' : 'text-[var(--_muted-fg)] hover:text-[var(--_fg)]',
          ].join(' ')}
        >
          Just show me a weekend's events
        </button>
      </div>

      {mode === 'state' ? (
        <>
          <label htmlFor="leave-planner-state" className="mb-1.5 block text-sm font-semibold text-[var(--_fg)]">
            1. Home state
          </label>
          <select
            id="leave-planner-state"
            value={state}
            onChange={(e) => handleStateChange(e.target.value)}
            className="input w-full rounded-xl border border-[var(--_border)] bg-[var(--_card)] px-3 py-2.5 text-sm text-[var(--_fg)] focus:border-[var(--_primary)] focus:outline-none"
          >
            <option value="">Select your state or UT…</option>
            {INDIAN_STATES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          {loadingWindows && (
            <p className="mt-3 flex items-center gap-1.5 text-sm text-[var(--_muted-fg)]">
              <Loader2 size={14} className="animate-spin" /> Loading long weekends…
            </p>
          )}
          {windowsError && (
            <p className="mt-3 text-sm text-red-600">{windowsError}</p>
          )}
          {!loadingWindows && state && longWeekends.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-sm font-semibold text-[var(--_fg)]">2. Pick one long weekend</p>
              <LongWeekendList windows={longWeekends} onSelect={setSelectedWindow} selected={selectedWindow} />
            </div>
          )}
        </>
      ) : (
        <>
          <p className="mb-1.5 text-sm font-semibold text-[var(--_fg)]">1. Pick a weekend</p>
          <WeekendQuickPicker selected={selectedWeekend} onSelect={setSelectedWeekend} />
        </>
      )}

      {dateRange && (
        <div className="mt-5">
          <p className="mb-2 text-sm font-semibold text-[var(--_fg)]">
            {mode === 'state' ? '3. What are you into?' : '2. What are you into?'} <span className="font-normal text-[var(--_muted-fg)]">(optional)</span>
          </p>
          <InterestPicker selected={interests} onToggle={toggleInterest} />

          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className="btn btn-accent mt-6 w-full gap-2 rounded-xl py-3 text-sm font-bold disabled:opacity-50"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : null}
            {mode === 'state' ? 'Show me events for this weekend' : 'Show me events across India'}
          </button>
        </div>
      )}
    </div>
  )
}
