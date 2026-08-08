import { describe, it, expect } from 'vitest'
import { formatCurrency, formatDayDate, maskEmail } from '@/lib/format'

describe('maskEmail', () => {
  it('keeps two characters of the local part and domain, plus the TLD', () => {
    expect(maskEmail('priya.sharma@gmail.com')).toBe('pr•••@gm•••.com')
  })

  it('never echoes the full address for short local parts', () => {
    // The head is kept verbatim when it is already <= 2 chars, so assert the
    // masking itself still happened rather than that some prefix survived.
    expect(maskEmail('jo@outlook.com')).toBe('jo•••@ou•••.com')
    expect(maskEmail('a@b.io')).toBe('a•••@b•••.io')
  })

  it('preserves multi-part TLDs', () => {
    expect(maskEmail('kunal@wanderplanner.co.in')).toBe('ku•••@wa•••.in')
  })

  it('masks entirely when the input is not address-shaped', () => {
    // Anything unrecognised must not fall through to the screen verbatim.
    expect(maskEmail('not-an-email')).toBe('•••')
    expect(maskEmail('trailing@')).toBe('•••')
    expect(maskEmail('')).toBe('•••')
  })

  it('masks a domain with no dot at all', () => {
    expect(maskEmail('someone@localhost')).toBe('so•••@lo•••')
  })
})

describe('formatCurrency', () => {
  it('formats INR with Indian digit grouping and rupee symbol', () => {
    expect(formatCurrency(150000, 'INR')).toBe('₹1,50,000')
  })

  it('defaults to INR', () => {
    expect(formatCurrency(1800)).toBe('₹1,800')
  })

  it('rounds to whole units', () => {
    expect(formatCurrency(999.6, 'INR')).toBe('₹1,000')
  })

  it('formats foreign currencies with en-IN grouping', () => {
    expect(formatCurrency(1234567, 'USD')).toContain('12,34,567')
  })

  it('degrades to a plain label for malformed currency codes', () => {
    expect(formatCurrency(1500, 'not-a-code')).toBe('not-a-code 1,500')
  })
})

describe('formatDayDate', () => {
  it('formats ISO dates as human day-dates', () => {
    expect(formatDayDate('2026-11-14')).toBe('Sat, 14 Nov')
  })

  it('returns empty string for empty input', () => {
    expect(formatDayDate('')).toBe('')
  })

  it('returns non-ISO input unchanged', () => {
    expect(formatDayDate('Day one')).toBe('Day one')
  })
})
