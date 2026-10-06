import * as React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LeavePlannerFlow } from '@/components/leave-planner/LeavePlannerFlow'
import type { LongWeekendWindow, WorkationRecommendResponse } from '@/types'

const getLongWeekends = vi.fn()
const getWorkationRecommendations = vi.fn()
vi.mock('@/lib/api', () => ({
  getLongWeekends: (...args: unknown[]) => getLongWeekends(...args),
  getWorkationRecommendations: (...args: unknown[]) => getWorkationRecommendations(...args),
}))

beforeEach(() => {
  vi.clearAllMocks()
})


const WINDOWS: LongWeekendWindow[] = [
  {
    start_date: '2026-11-14',
    end_date: '2026-11-16',
    total_days_off: 3,
    leave_days_needed: 0,
    reason: 'Weekend + Karnataka Rajyotsava',
    value: 3,
  },
]

const RECOMMENDATIONS: WorkationRecommendResponse = {
  long_weekends: [
    { start_date: '2026-11-14', end_date: '2026-11-16', total_days_off: 3, leave_days_needed: 0, reason: 'Weekend + Karnataka Rajyotsava', value: 3 },
  ],
  destinations: [],
  has_results: true,
  message: '',
}

describe('LeavePlannerFlow', () => {
  describe('"plan around my long weekends" mode (default)', () => {
    it('fetches long weekends for the chosen state and renders them as selectable options', async () => {
      getLongWeekends.mockResolvedValue(WINDOWS)
      render(<LeavePlannerFlow onResults={vi.fn()} onError={vi.fn()} />)

      await userEvent.selectOptions(screen.getByLabelText(/home state/i), 'Karnataka')

      expect(getLongWeekends).toHaveBeenCalledWith('Karnataka')
      expect(await screen.findByRole('option', { name: /2026-11-14/ })).toBeInTheDocument()
      // Interests/submit step isn't shown until a specific window is picked.
      expect(screen.queryByRole('button', { name: /show me events for this weekend/i })).not.toBeInTheDocument()
    })

    it('picking a window reveals interests + submit, and submits state + interests + the picked window as date_range', async () => {
      getLongWeekends.mockResolvedValue(WINDOWS)
      getWorkationRecommendations.mockResolvedValue(RECOMMENDATIONS)
      const onResults = vi.fn()

      render(<LeavePlannerFlow onResults={onResults} onError={vi.fn()} />)

      await userEvent.selectOptions(screen.getByLabelText(/home state/i), 'Karnataka')
      await userEvent.click(await screen.findByRole('option', { name: /2026-11-14/ }))
      await userEvent.click(screen.getByRole('button', { name: 'Culture' }))
      await userEvent.click(screen.getByRole('button', { name: /show me events for this weekend/i }))

      expect(getWorkationRecommendations).toHaveBeenCalledWith(
        'Karnataka', ['Culture'], ['2026-11-14', '2026-11-16'],
      )
      expect(onResults).toHaveBeenCalledWith(RECOMMENDATIONS)
    })

    it('reports an error up instead of throwing when getLongWeekends fails', async () => {
      getLongWeekends.mockRejectedValue(new Error('network'))
      render(<LeavePlannerFlow onResults={vi.fn()} onError={vi.fn()} />)

      await userEvent.selectOptions(screen.getByLabelText(/home state/i), 'Goa')

      expect(await screen.findByText(/couldn't load long weekends/i)).toBeInTheDocument()
    })
  })

  describe('"just show me a weekend\'s events" mode', () => {
    it('lets the user pick a weekend with no state, then submits with state=null', async () => {
      getWorkationRecommendations.mockResolvedValue(RECOMMENDATIONS)
      const onResults = vi.fn()

      render(<LeavePlannerFlow onResults={onResults} onError={vi.fn()} />)

      await userEvent.click(screen.getByRole('tab', { name: /just show me a weekend's events/i }))
      // Quick-pick chips are rendered with a "Sat, <date> – Sun, <date>" label;
      // just grab the first one rather than asserting on computed dates.
      const quickPicks = screen.getAllByRole('button', { name: /–/ })
      await userEvent.click(quickPicks[0])
      await userEvent.click(screen.getByRole('button', { name: /show me events across india/i }))

      expect(getLongWeekends).not.toHaveBeenCalled()
      expect(getWorkationRecommendations).toHaveBeenCalledWith(
        null, [], expect.arrayContaining([expect.any(String), expect.any(String)]),
      )
      expect(onResults).toHaveBeenCalledWith(RECOMMENDATIONS)
    })

    it('switching modes resets the selection and hides the submit step', async () => {
      getLongWeekends.mockResolvedValue(WINDOWS)
      render(<LeavePlannerFlow onResults={vi.fn()} onError={vi.fn()} />)

      await userEvent.selectOptions(screen.getByLabelText(/home state/i), 'Karnataka')
      await userEvent.click(await screen.findByRole('option', { name: /2026-11-14/ }))
      expect(screen.getByRole('button', { name: /show me events for this weekend/i })).toBeInTheDocument()

      await userEvent.click(screen.getByRole('tab', { name: /just show me a weekend's events/i }))

      expect(screen.queryByRole('button', { name: /show me events/i })).not.toBeInTheDocument()
    })
  })
})
