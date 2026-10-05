import * as React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HomeStateInterestForm } from '@/components/workation/HomeStateInterestForm'
import type { LongWeekendWindow, WorkationRecommendResponse } from '@/types'

const getLongWeekends = vi.fn()
const getWorkationRecommendations = vi.fn()
vi.mock('@/lib/api', () => ({
  getLongWeekends: (...args: unknown[]) => getLongWeekends(...args),
  getWorkationRecommendations: (...args: unknown[]) => getWorkationRecommendations(...args),
}))

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
  long_weekends: WINDOWS,
  destinations: [],
  has_results: true,
  message: '',
}

describe('HomeStateInterestForm', () => {
  it('disables submit until a state is chosen', () => {
    render(<HomeStateInterestForm onResults={vi.fn()} onError={vi.fn()} />)
    expect(screen.getByRole('button', { name: /find my next long weekend/i })).toBeDisabled()
  })

  it('calls getLongWeekends + getWorkationRecommendations with the chosen state/interests and reports results up', async () => {
    getLongWeekends.mockResolvedValue(WINDOWS)
    getWorkationRecommendations.mockResolvedValue(RECOMMENDATIONS)
    const onResults = vi.fn()

    render(<HomeStateInterestForm onResults={onResults} onError={vi.fn()} />)

    await userEvent.selectOptions(screen.getByLabelText(/home state/i), 'Karnataka')
    await userEvent.click(screen.getByRole('button', { name: 'Culture' }))
    await userEvent.click(screen.getByRole('button', { name: /find my next long weekend/i }))

    expect(getLongWeekends).toHaveBeenCalledWith('Karnataka')
    expect(getWorkationRecommendations).toHaveBeenCalledWith('Karnataka', ['Culture'])
    expect(onResults).toHaveBeenCalledWith('Karnataka', WINDOWS, RECOMMENDATIONS)
  })

  it('reports an error up instead of throwing when the API calls fail', async () => {
    getLongWeekends.mockRejectedValue(new Error('network'))
    getWorkationRecommendations.mockResolvedValue(RECOMMENDATIONS)
    const onError = vi.fn()

    render(<HomeStateInterestForm onResults={vi.fn()} onError={onError} />)

    await userEvent.selectOptions(screen.getByLabelText(/home state/i), 'Goa')
    await userEvent.click(screen.getByRole('button', { name: /find my next long weekend/i }))

    expect(onError).toHaveBeenCalledWith(expect.stringMatching(/couldn't load/i))
  })
})
