import * as React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BookingExpensesPanel } from '@/components/dashboard/BookingExpensesPanel'
import { useTripConfigStore } from '@/store/tripConfigStore'

// Each child is exercised by its own tests (or is network-bound). What this
// panel is responsible for is *which* sections appear, in what order, and
// under which conditions — so the children are stubbed to identifiable marks.
vi.mock('@/components/dashboard/ExpenseBreakupCard', () => ({
  ExpenseBreakupCard: () => <div data-testid="expenses" />,
}))
vi.mock('@/components/dashboard/BookingHub', () => ({
  BookingHub: () => <div data-testid="my-bookings" />,
}))
vi.mock('@/components/dashboard/CurrencyWidget', () => ({
  CurrencyWidget: () => <div data-testid="currency" />,
}))
vi.mock('@/components/itinerary/AgentHandoffCard', () => ({
  AgentHandoffCard: () => <div data-testid="local-expert" />,
}))
vi.mock('@/components/itinerary/BookingLinksSection', () => ({
  BookingLinksSection: () => <div data-testid="book-this-trip" />,
}))

describe('BookingExpensesPanel', () => {
  beforeEach(() => {
    useTripConfigStore.getState().resetConfig()
  })

  it('groups expenses, expert help, booking links and saved bookings together', () => {
    // The v10.56.0 regrouping: these four were split across the old Overview
    // panel and the map sidebar two tabs away.
    useTripConfigStore.getState().setDestination({ city: 'Tokyo', country: 'JP', lat: 35.6, lon: 139.6 })

    render(<BookingExpensesPanel />)

    expect(screen.getByTestId('expenses')).toBeInTheDocument()
    expect(screen.getByTestId('local-expert')).toBeInTheDocument()
    expect(screen.getByTestId('book-this-trip')).toBeInTheDocument()
    expect(screen.getByTestId('my-bookings')).toBeInTheDocument()
  })

  it('orders the sections by the decision sequence', () => {
    // What will it cost → who can help → where do I book → what have I booked.
    useTripConfigStore.getState().setDestination({ city: 'Tokyo', country: 'JP', lat: 35.6, lon: 139.6 })

    const { container } = render(<BookingExpensesPanel />)
    const order = Array.from(container.querySelectorAll('[data-testid]')).map(
      (el) => el.getAttribute('data-testid'),
    )

    expect(order).toEqual(['expenses', 'local-expert', 'book-this-trip', 'my-bookings', 'currency'])
  })

  it('falls back to the country when no city is resolved', () => {
    useTripConfigStore.setState((s) => ({
      config: { ...s.config, destination: null, destination_country: 'Japan' },
    }))

    render(<BookingExpensesPanel />)

    expect(screen.getByTestId('expenses')).toBeInTheDocument()
  })

  it('shows only saved bookings when there is no destination yet', () => {
    // Expenses and booking links have nothing to price or link to, but saved
    // bookings are trip-independent and must not disappear.
    useTripConfigStore.setState((s) => ({
      config: { ...s.config, destination: null, destination_country: null },
    }))

    render(<BookingExpensesPanel />)

    expect(screen.getByTestId('my-bookings')).toBeInTheDocument()
    expect(screen.queryByTestId('expenses')).toBeNull()
    expect(screen.queryByTestId('local-expert')).toBeNull()
    expect(screen.queryByTestId('book-this-trip')).toBeNull()
  })
})
