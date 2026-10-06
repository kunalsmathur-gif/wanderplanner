'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { HomeStateInterestForm } from '@/components/workation/HomeStateInterestForm'
import { WorkationMapWrapper } from '@/components/workation/WorkationMapWrapper'
import { LongWeekendList } from '@/components/workation/LongWeekendList'
import { EventsAroundYou } from '@/components/workation/EventsAroundYou'
import { DestinationShortlist } from '@/components/workation/DestinationShortlist'
import { WorkationLogistics } from '@/components/workation/WorkationLogistics'
import { PlanThisTripCTA } from '@/components/workation/PlanThisTripCTA'
import { logClientEvent } from '@/lib/analyticsBeacon'
import { usePlanThisTrip } from '@/lib/workationHandoff'
import type { DestinationCandidate, LongWeekendWindow, WorkationRecommendResponse } from '@/types'

/**
 * Standalone discovery surface for the "India Workation & Long Weekend
 * Finder" (docs/plans/india-workation-finder-plan.md) — deliberately
 * separate from the Anya wizard. A user picks a home state + interests,
 * sees upcoming long weekends and candidate destinations plotted on a map
 * (the primary visual/selection surface per the plan's addendum) with the
 * same data available as accessible list cards, then hands off a chosen
 * destination + window into the existing wizard via `PlanThisTripCTA`.
 */
export default function WorkationPage() {
  const [longWeekends, setLongWeekends] = useState<LongWeekendWindow[]>([])
  const [recommendations, setRecommendations] = useState<WorkationRecommendResponse | null>(null)
  const [selectedDestination, setSelectedDestination] = useState<DestinationCandidate | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hasSearched, setHasSearched] = useState(false)
  const planThisTrip = usePlanThisTrip()

  useEffect(() => {
    logClientEvent('workation_view')
  }, [])

  function handleResults(
    _state: string,
    windows: LongWeekendWindow[],
    results: WorkationRecommendResponse,
  ) {
    setLongWeekends(windows)
    setRecommendations(results)
    setSelectedDestination(results.destinations[0] ?? null)
    setError(null)
    setHasSearched(true)
    logClientEvent('workation_recommend', {
      has_results: results.has_results,
      destination_count: results.destinations.length,
    })
  }

  function handleError(message: string) {
    setError(message)
  }

  const destinations = recommendations?.destinations ?? []
  // All candidate destinations are matched against the best-ranked window
  // (apps/api/chains/workation_recommend_chain.py uses `windows[0]` as
  // `top_window` for every destination in a single response) — so the first
  // long-weekend summary is always the right one to hand off alongside any
  // selected destination.
  const matchedLongWeekend = recommendations?.long_weekends[0] ?? null

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
      <div className="flex items-center gap-2">
        <Link href="/" className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--_muted-fg)] hover:text-[var(--_primary)]">
          <ArrowLeft size={16} /> Back
        </Link>
      </div>

      <div>
        <h1 className="font-display text-2xl font-black text-[var(--_fg)] sm:text-3xl">
          Find your next long weekend
        </h1>
        <p className="mt-1.5 max-w-xl text-sm text-[var(--_muted-fg)]">
          Tell us your home state and interests — we'll find upcoming long weekends, what's
          happening around India that matches your interests, and where a workation (a few
          WFH days + the weekend) fits best.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <div className="flex flex-col gap-5">
          <HomeStateInterestForm onResults={handleResults} onError={handleError} />

          {error && (
            <p className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {error}
            </p>
          )}

          {hasSearched && recommendations && !recommendations.has_results && (
            <p className="rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-4 text-sm text-[var(--_muted-fg)]">
              {recommendations.message || 'Nothing found for this state/interests yet — try a different state or broaden your interests.'}
            </p>
          )}

          {hasSearched && (
            <>
              <section>
                <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--_muted-fg)]">
                  Upcoming long weekends
                </h2>
                <LongWeekendList windows={longWeekends} />
              </section>

              {destinations.length > 0 && (
                <section>
                  <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--_muted-fg)]">
                    Destinations for you
                  </h2>
                  <DestinationShortlist
                    destinations={destinations}
                    selectedDestination={selectedDestination}
                    onSelectDestination={setSelectedDestination}
                    onPlanThisTrip={(d) => planThisTrip(d, matchedLongWeekend)}
                  />
                </section>
              )}
            </>
          )}
        </div>

        <div className="flex flex-col gap-5">
          <WorkationMapWrapper
            destinations={destinations}
            selectedDestination={selectedDestination}
            onSelectDestination={setSelectedDestination}
            onPlanThisTrip={(d) => planThisTrip(d, matchedLongWeekend)}
          />

          {selectedDestination && (
            <div className="rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-lg font-bold text-[var(--_fg)]">{selectedDestination.destination}</h2>
                <PlanThisTripCTA destination={selectedDestination} longWeekend={matchedLongWeekend} />
              </div>
              <div className="mt-4">
                <WorkationLogistics destination={selectedDestination} />
              </div>
            </div>
          )}

          {hasSearched && (
            <section>
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--_muted-fg)]">
                Events around you
              </h2>
              <EventsAroundYou destinations={destinations} />
            </section>
          )}

          {!hasSearched && (
            <div className="flex h-40 items-center justify-center gap-2 rounded-2xl border border-dashed border-[var(--_border)] text-sm text-[var(--_muted-fg)]">
              <Loader2 size={16} className="opacity-0" />
              Pick a state and interests to see results on the map.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
