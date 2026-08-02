import * as React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThreeColumnLayout } from '@/components/layout/ThreeColumnLayout'
import { useAppStore } from '@/store/appStore'
import { useChatStore } from '@/store/chatStore'
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
    useChatStore.setState({ isOpen: false } as never)
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

  // The bar used to sit at the end of the scroll flow, so on a phone you only
  // reached it by scrolling to the very bottom of the panel. It is now frozen
  // to the viewport bottom.
  it('freezes the tab bar to the bottom of the viewport', () => {
    render(<ThreeColumnLayout />)

    const tabs = screen.getByRole('navigation', { name: 'Dashboard sections' })
    expect(tabs).toHaveClass('fixed', 'bottom-0', 'inset-x-0')
  })

  it('keeps the tab bar under the orb, popup and chat panel', () => {
    // z-30 is deliberate: the Anya orb (z-40), feedback popup (z-50) and chat
    // panel (z-9998) are all meant to sit over the whole page, including this.
    render(<ThreeColumnLayout />)

    expect(screen.getByRole('navigation', { name: 'Dashboard sections' })).toHaveClass('z-30')
  })

  it('reserves scroll-container space for the frozen bar and the orb', () => {
    // Both are `fixed`, so neither takes space in the flow. When this number
    // and the orb disagree, the orb sits on the last card's CTA and wins the
    // tap — which is exactly how it covered "Get Quotation" before v10.56.1.
    const { container } = render(<ThreeColumnLayout />)
    const scroller = container.querySelector('.overflow-y-auto')

    expect(scroller?.className).toMatch(/pb-\[calc\(7rem\+env\(safe-area-inset-bottom\)\)\]/)
  })

  it('clears the home indicator on notched phones', () => {
    // The previous `pb-safe` spacer was a no-op — no such utility exists in
    // globals.css or the theme, so the labels sat under the home indicator.
    render(<ThreeColumnLayout />)

    expect(screen.getByRole('navigation', { name: 'Dashboard sections' })).toHaveClass(
      'pb-[env(safe-area-inset-bottom)]'
    )
  })

  it('keeps Anya out of the title bar', () => {
    // The v10.58 title-bar button was a stand-in while the orb was off mobile.
    // The orb is back (smaller), so a second trigger would just be clutter in
    // a row that already holds Theme, Share and Account.
    render(<ThreeColumnLayout />)

    expect(screen.queryByRole('button', { name: /Open Anya/i })).not.toBeInTheDocument()
  })

  it('marks the active tab for assistive technology', async () => {
    render(<ThreeColumnLayout />)

    const bookings = screen.getByRole('button', { name: /Booking & Expenses/i })
    expect(bookings).not.toHaveAttribute('aria-current')

    await userEvent.click(bookings)
    expect(screen.getByRole('button', { name: /Booking & Expenses/i })).toHaveAttribute('aria-current', 'page')
  })
})
