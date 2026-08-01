'use client'

import { useTripConfigStore } from '@/store/tripConfigStore'
import { CurrencyWidget } from '@/components/dashboard/CurrencyWidget'
import { ExpenseBreakupCard } from '@/components/dashboard/ExpenseBreakupCard'
import { BookingHub } from '@/components/dashboard/BookingHub'
import { AgentHandoffCard } from '@/components/itinerary/AgentHandoffCard'
import { BookingLinksSection } from '@/components/itinerary/BookingLinksSection'

/**
 * Everything about paying for and booking the trip, in one place.
 *
 * Was `Column1Metrics` — a panel that had drifted into holding trip metrics,
 * the whole-trip actions, expenses *and* the expert handoff, while the actual
 * booking links and saved bookings sat two tabs away under the map. v10.56.0
 * regrouped by what the user is trying to do: the metrics and actions moved to
 * the itinerary itself (`TripSummaryHeader`), and the booking sections moved
 * here from `Column3Sidebar`.
 *
 * Order is deliberate and follows the decision sequence — what will it cost,
 * who can help me, where do I book, what have I already booked.
 */
export function BookingExpensesPanel() {
  const destination = useTripConfigStore((state) => state.config.destination)
  const destinationCountry = useTripConfigStore((state) => state.config.destination_country)
  const budget = useTripConfigStore((state) => state.config.budget)

  const hasDestination = Boolean(destination?.city || destinationCountry)

  return (
    <div className="space-y-4 p-4">
      {hasDestination ? (
        <>
          {/* Collapsed by default (ExpenseBreakupCard owns that state) — it is
              the tallest thing here and most users only want the total. */}
          <ExpenseBreakupCard />

          <div className="border-t border-[var(--_border)] pt-3">
            <AgentHandoffCard />
          </div>

          <div className="border-t border-[var(--_border)] pt-3">
            <BookingLinksSection />
          </div>

          <div className="border-t border-[var(--_border)] pt-3">
            <BookingHub />
          </div>

          <div className="border-t border-[var(--_border)] pt-3">
            <CurrencyWidget baseCurrency={budget.currency} />
          </div>
        </>
      ) : (
        <>
          {/* No destination yet: the booking and expense sections have nothing
              to price or link to, but saved bookings are trip-independent. */}
          <BookingHub />
        </>
      )}
    </div>
  )
}
