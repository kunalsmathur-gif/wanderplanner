'use client'

import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { getLongWeekends, getWorkationRecommendations } from '@/lib/api'
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

// Reuses the same interest/theme vocabulary already used by the wizard's
// theme chips (see THEME_CHIP_KEYWORDS in components/wizard/LLMWizard.tsx)
// so a user's mental model of "interests" stays consistent across surfaces.
const INTERESTS = [
  'Culture', 'Nature', 'Food', 'Adventure', 'Shopping', 'Photography',
  'Nightlife', 'Sports', 'Wellness', 'Religious',
] as const

interface Props {
  onResults: (state: string, longWeekends: LongWeekendWindow[], recommendations: WorkationRecommendResponse) => void
  onError: (message: string) => void
}

export function HomeStateInterestForm({ onResults, onError }: Props) {
  const [state, setState] = useState('')
  const [interests, setInterests] = useState<Set<string>>(new Set())
  const [submitting, setSubmitting] = useState(false)

  function toggleInterest(interest: string) {
    setInterests((prev) => {
      const next = new Set(prev)
      if (next.has(interest)) next.delete(interest)
      else next.add(interest)
      return next
    })
  }

  async function handleSubmit() {
    if (!state || submitting) return
    setSubmitting(true)
    try {
      const selectedInterests = Array.from(interests)
      const [longWeekends, recommendations] = await Promise.all([
        getLongWeekends(state),
        getWorkationRecommendations(state, selectedInterests),
      ])
      onResults(state, longWeekends, recommendations)
    } catch {
      onError("Couldn't load long weekends for this state right now — please try again in a moment.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-5 sm:p-6">
      <label htmlFor="workation-state" className="mb-1.5 block text-sm font-semibold text-[var(--_fg)]">
        Home state
      </label>
      <select
        id="workation-state"
        value={state}
        onChange={(e) => setState(e.target.value)}
        className="input w-full rounded-xl border border-[var(--_border)] bg-[var(--_card)] px-3 py-2.5 text-sm text-[var(--_fg)] focus:border-[var(--_primary)] focus:outline-none"
      >
        <option value="">Select your state or UT…</option>
        {INDIAN_STATES.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>

      <p className="mb-2 mt-5 text-sm font-semibold text-[var(--_fg)]">What are you into?</p>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Interests">
        {INTERESTS.map((interest) => {
          const isSelected = interests.has(interest)
          return (
            <button
              key={interest}
              type="button"
              onClick={() => toggleInterest(interest)}
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

      <button
        type="button"
        onClick={handleSubmit}
        disabled={!state || submitting}
        className="btn btn-accent mt-6 w-full gap-2 rounded-xl py-3 text-sm font-bold disabled:opacity-50"
      >
        {submitting ? <Loader2 size={16} className="animate-spin" /> : null}
        Find my next long weekend
      </button>
    </div>
  )
}
