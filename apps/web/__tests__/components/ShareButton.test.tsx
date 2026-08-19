import * as React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ShareButton } from '@/components/common/ShareButton'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { shareTrip } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  shareTrip: vi.fn(),
}))

const initialItineraryState = useItineraryStore.getState()
const initialTripConfigState = useTripConfigStore.getState()

describe('ShareButton — generation_id passthrough (issue #34)', () => {
  beforeEach(() => {
    vi.mocked(shareTrip).mockReset()
    vi.mocked(shareTrip).mockResolvedValue({ slug: 'abc', url: '/share/abc' })
    if (!('clipboard' in navigator) || !navigator.clipboard?.writeText) {
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: vi.fn() },
        configurable: true,
      })
    }
  })

  afterEach(() => {
    useItineraryStore.setState(initialItineraryState)
    useTripConfigStore.setState(initialTripConfigState)
  })

  it('includes the current generationId when sharing', async () => {
    useItineraryStore.setState({
      ...initialItineraryState,
      days: [{ day_number: 1, date: '2026-01-01', theme: 'Arrival', items: [], transit_warnings: [] }],
      generationId: 'gen-123',
    })

    render(<ShareButton />)
    await userEvent.setup().click(screen.getByRole('button'))

    await waitFor(() => expect(shareTrip).toHaveBeenCalled())
    expect(shareTrip).toHaveBeenCalledWith(
      expect.objectContaining({ generation_id: 'gen-123' }),
    )
  })

  it('shares with generation_id undefined when the generation was never stored', async () => {
    useItineraryStore.setState({
      ...initialItineraryState,
      days: [{ day_number: 1, date: '2026-01-01', theme: 'Arrival', items: [], transit_warnings: [] }],
      generationId: undefined,
    })

    render(<ShareButton />)
    await userEvent.setup().click(screen.getByRole('button'))

    await waitFor(() => expect(shareTrip).toHaveBeenCalled())
    expect(shareTrip).toHaveBeenCalledWith(
      expect.objectContaining({ generation_id: undefined }),
    )
  })
})
