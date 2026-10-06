import * as React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WeekendQuickPicker } from '@/components/leave-planner/WeekendQuickPicker'

describe('WeekendQuickPicker', () => {
  const originalTZ = process.env.TZ

  beforeEach(() => {
    // Regression test for a timezone bug: the quick-pick dates were built with
    // local calendar math but serialized via `toISOString()`, which converts
    // to UTC first. In IST (UTC+5:30) that shifts local Saturday 00:00 back
    // to Friday 18:30 UTC, silently turning every "Saturday-Sunday" quick
    // pick into "Friday-Saturday" in the submitted date_range.
    process.env.TZ = 'Asia/Kolkata'
  })

  afterEach(() => {
    process.env.TZ = originalTZ
  })

  it('offers Saturday-Sunday quick picks, not Friday-Saturday, when the local timezone is IST', () => {
    render(<WeekendQuickPicker selected={null} onSelect={vi.fn()} />)

    const group = screen.getByRole('group', { name: /upcoming weekends/i })
    const firstPick = group.querySelectorAll('button')[0]
    expect(firstPick).toBeTruthy()

    expect(firstPick?.textContent).toMatch(/^sat/i)
    expect(firstPick?.textContent).toMatch(/sun/i)
    expect(firstPick?.textContent).not.toMatch(/fri/i)
  })

  it('reports the selected range as the Saturday followed immediately by the Sunday (not shifted a day earlier)', async () => {
    const onSelect = vi.fn()
    render(<WeekendQuickPicker selected={null} onSelect={onSelect} />)

    const group = screen.getByRole('group', { name: /upcoming weekends/i })
    const firstPick = group.querySelectorAll('button')[0] as HTMLButtonElement
    await userEvent.click(firstPick)

    expect(onSelect).toHaveBeenCalledTimes(1)
    const range = onSelect.mock.calls[0][0] as { start: string; end: string }

    const start = new Date(range.start + 'T00:00:00')
    const end = new Date(range.end + 'T00:00:00')
    expect(start.getDay()).toBe(6) // Saturday
    expect(end.getDay()).toBe(0) // Sunday
    expect(end.getTime() - start.getTime()).toBe(24 * 60 * 60 * 1000) // consecutive days
  })
})
