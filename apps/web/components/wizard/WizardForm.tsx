'use client'

import { useState } from 'react'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useAppStore } from '@/store/appStore'
import { streamItinerary } from '@/lib/api'
import { PurposeSection } from './sections/PurposeSection'
import { TimingSection } from './sections/TimingSection'
import { DestinationSection } from './sections/DestinationSection'
import { PersonaSection } from './sections/PersonaSection'
import { GroupSection } from './sections/GroupSection'
import { AccommodationSection } from './sections/AccommodationSection'
import { PaceBudgetSection } from './sections/PaceBudgetSection'

function isConfigValid(config: ReturnType<typeof useTripConfigStore.getState>['config']) {
  return (
    config.purpose.length > 0 &&
    config.origin.city.length > 0 &&
    config.budget.amount > 0 &&
    (config.dates.start !== null || config.dates.flexible)
  )
}

export function WizardForm() {
  const config = useTripConfigStore((s) => s.config)
  const effectivePace = useTripConfigStore((s) => s.effectivePace)
  const { setStatus, setProgress, setDays, setError } = useItineraryStore()
  const goToStep = useAppStore((s) => s.goToStep)
  const [submitting, setSubmitting] = useState(false)

  const valid = isConfigValid(config)

  function handleGenerate() {
    if (!valid || submitting) return
    setSubmitting(true)
    setStatus('loading')
    goToStep(2)

    streamItinerary(
      { ...config, pace: effectivePace() },
      (msg, step, total) => setProgress({ message: msg, step, total }),
      (result) => {
        setDays(result.days, result.alignment_score)
        setSubmitting(false)
        // Stay at step 2 — ItineraryOverview shows day summary; user clicks Finalize → step 3
      },
      (code, message, retryable) => {
        setError({ code, message, retryable })
        setSubmitting(false)
        goToStep(2)
      },
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-8">
        <div>
          <h1 className="text-3xl font-bold text-[#0F172A]">Plan Your Trip</h1>
          <p className="mt-1 text-sm text-slate-500">
            Fill in your trip details below. All fields marked * are required.
          </p>
        </div>

        <PurposeSection />
        <TimingSection />
        <DestinationSection />
        <PersonaSection />
        <GroupSection />
        <AccommodationSection />
        <PaceBudgetSection />

        <div className="pb-10">
          <button
            onClick={handleGenerate}
            disabled={!valid || submitting}
            className={[
              'w-full h-12 rounded-lg font-semibold text-white transition-all',
              valid && !submitting
                ? 'bg-[#1E40AF] hover:bg-blue-800 cursor-pointer'
                : 'bg-slate-300 cursor-not-allowed opacity-60',
            ].join(' ')}
          >
            {submitting ? 'Generating your itinerary…' : 'Generate Itinerary →'}
          </button>
          {!valid && (
            <p className="mt-2 text-xs text-slate-400 text-center">
              Please fill in Purpose, Origin, a date or season, and Budget to continue.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
