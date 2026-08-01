import * as React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThreeColumnLayout } from '@/components/layout/ThreeColumnLayout'
import { useAppStore } from '@/store/appStore'
import { useItineraryStore } from '@/store/itineraryStore'

// The panels have their own tests; this file is about the mobile information
// architecture — the three tab names and which panel each one shows.
vi.mock('@/components/dashboard/BookingExpensesPanel', () => ({
  BookingExpensesPanel: () => <div data-testid="panel-bookings" />,
}))
vi.mock('@/components/itinerary/TripSummaryHeader', () => ({
  TripSummaryHeader: () => <div data-testid="panel-trip-summary" />,
}))
vi.mock('@/components/itinerary/ItineraryTimeline', () => ({
  ItineraryTimeline: () => <div data-testid="panel-timeline" />,
}))
vi.mock('@/components/itinerary/Column3Sidebar', () => ({
  Column3Sidebar: () => <div data-testid="panel-map-tips" />,
}))
vi.mock('@/components/comparison/ComparisonPanel', () => ({
  ComparisonPanel: () => <div data-testid="panel-comparison" />,
}))
vi.mock('@/components/map/MapWrapper', () => ({ MapWrapper: () => <div /> }))
vi.mock('@/components/common/ShareButton', () => ({ ShareButton: () => <button type="button">Share</button> }))
vi.mock('@/components/common/ThemeToggle', () => ({ ThemeToggle: () => <button type="button">Theme</button> }))
vi.mock('@/components/common/UserMenu', () => ({ UserMenu: () => <div /> }))
vi.mock('@/components/itinerary/TripFeedbackPopup', () => ({ TripFeedbackPopup: () => null }))

const day = (n: number) => ({ day_number: n, date: '2026-01-0' + n, theme: 't', items: [] })

describe('ThreeColumnLayout — mobile tabs', () => {
  beforeEach(() => {
    useItineraryStore.getState().reset()
    useItineraryStore.getState().setDays([day(1)] as never, 80)
    useAppStore.setState({ mobileTab: 'itinerary', step3View: 'itinerary', wizardOpen: false } as never)
  })

  it('names the three sections Itinerary, Booking & Expenses, and Maps & Tips', () => {
    // "Overview" was renamed in v10.56.0 — it described where the content sat,
    // not what it was for, and the panel no longer holds trip metrics at all.
    render(<ThreeColumnLayout />)

    const tabs = screen.getByRole('navigation', { name: 'Dashboard sections' })
    expect(tabs).toHaveTextContent('Itinerary')
    expect(tabs).toHaveTextContent('Booking & Expenses')
    expect(tabs).toHaveTextContent('Maps & Tips')
    expect(tabs).not.toHaveTextContent('Overview')
  })

  it('puts the trip summary above the day-by-day breakdown', () => {
    // The ordering is the ask: metrics and whole-trip actions first, then days.
    const { container } = render(<ThreeColumnLayout />)
    const order = Array.from(container.querySelectorAll('[data-testid]'))
      .map((el) => el.getAttribute('data-testid'))
      .filter((id) => id === 'panel-trip-summary' || id === 'panel-timeline')

    expect(order.slice(0, 2)).toEqual(['panel-trip-summary', 'panel-timeline'])
  })

  it('switches panels when a tab is pressed', async () => {
    render(<ThreeColumnLayout />)

    await userEvent.click(screen.getByRole('button', { name: /Booking & Expenses/i }))
    expect(useAppStore.getState().mobileTab).toBe('bookings')

    await userEvent.click(screen.getByRole('button', { name: /Maps & Tips/i }))
    expect(useAppStore.getState().mobileTab).toBe('map')
  })

  it('marks the active tab for assistive technology', async () => {
    render(<ThreeColumnLayout />)

    const bookings = screen.getByRole('button', { name: /Booking & Expenses/i })
    expect(bookings).not.toHaveAttribute('aria-current')

    await userEvent.click(bookings)
    expect(screen.getByRole('button', { name: /Booking & Expenses/i })).toHaveAttribute('aria-current', 'page')
  })
})
