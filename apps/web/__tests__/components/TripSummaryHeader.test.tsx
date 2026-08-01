import * as React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TripSummaryHeader } from '@/components/itinerary/TripSummaryHeader'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useAppStore } from '@/store/appStore'
import { useFeedbackPromptStore } from '@/store/feedbackPromptStore'

// react-pdf is heavy and irrelevant here; the button's own behaviour is not
// what this component is responsible for.
vi.mock('@/components/pdf/PdfDownloadButton', () => ({
  PdfDownloadButton: () => <button type="button">Download PDF</button>,
}))

const day = (n: number) => ({ day_number: n, date: '2026-01-0' + n, theme: 't', items: [] })

function setTrip(partial: Record<string, unknown>) {
  useTripConfigStore.setState((s) => ({ config: { ...s.config, ...partial } }))
}

describe('TripSummaryHeader', () => {
  beforeEach(() => {
    useTripConfigStore.getState().resetConfig()
    useItineraryStore.getState().reset()
    useFeedbackPromptStore.setState({ ...useFeedbackPromptStore.getState() })
  })

  it('shows the three trip metrics with the itinerary alongside them', async () => {
    // These lived in the separate "Overview" tab before v10.56.0; the point of
    // the move is that they render with the day-by-day plan.
    setTrip({
      destination: { city: 'Tokyo', country: 'JP', lat: 35.6, lon: 139.6 },
      budget: { amount: 150000, currency: 'INR' },
    })
    useItineraryStore.getState().setDays([day(1), day(2), day(3)] as never, 87)

    render(<TripSummaryHeader />)

    expect(screen.getByText('Destination')).toBeInTheDocument()
    expect(screen.getByText('Tokyo')).toBeInTheDocument()
    expect(screen.getByText('Days')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Edit Trip/i })).toBeInTheDocument()
    // `next/dynamic` (ssr: false) shows its skeleton first, so this one
    // resolves asynchronously — the point is that both whole-trip actions sit
    // here, in the itinerary, rather than in the old Overview tab.
    expect(await screen.findByRole('button', { name: /Download PDF/i })).toBeInTheDocument()
  })

  describe('destination label fallback chain', () => {
    it('appends a hop count for multi-city trips', () => {
      setTrip({
        destination: { city: 'Tokyo', country: 'JP', lat: 35.6, lon: 139.6 },
        hops: [{ city: 'Kyoto', country: 'JP', lat: 35, lon: 135 }],
      })
      render(<TripSummaryHeader />)
      expect(screen.getByText('Tokyo +1')).toBeInTheDocument()
    })

    it('falls back to the country when no city is resolved yet', () => {
      setTrip({ destination: null, destination_country: 'Japan' })
      render(<TripSummaryHeader />)
      expect(screen.getByText('Japan')).toBeInTheDocument()
    })

    it('shows a dash rather than an empty cell when neither is known', () => {
      setTrip({ destination: null, destination_country: null })
      render(<TripSummaryHeader />)
      expect(screen.getByText('—')).toBeInTheDocument()
    })
  })

  describe('Edit Trip', () => {
    it('opens the wizard', async () => {
      render(<TripSummaryHeader />)
      await userEvent.click(screen.getByRole('button', { name: /Edit Trip/i }))
      expect(useAppStore.getState().wizardOpen).toBe(true)
    })

    it('asks for feedback on the plan being left behind', async () => {
      // Edit Trip is the closest analog to "back" in this UI, so it is the
      // moment to ask — but only when there is a plan to react to.
      const request = vi.fn()
      useFeedbackPromptStore.setState({ request } as never)
      useItineraryStore.getState().setDays([day(1)] as never, 50)

      render(<TripSummaryHeader />)
      await userEvent.click(screen.getByRole('button', { name: /Edit Trip/i }))

      expect(request).toHaveBeenCalledWith('back')
    })

    it('does not ask for feedback when no itinerary exists yet', async () => {
      const request = vi.fn()
      useFeedbackPromptStore.setState({ request } as never)
      useItineraryStore.getState().reset()

      render(<TripSummaryHeader />)
      await userEvent.click(screen.getByRole('button', { name: /Edit Trip/i }))

      expect(request).not.toHaveBeenCalled()
      expect(useAppStore.getState().wizardOpen).toBe(true)
    })
  })
})
