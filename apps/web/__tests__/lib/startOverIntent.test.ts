import { describe, it, expect } from 'vitest'
import { isStartOverIntent } from '@/lib/startOverIntent'

describe('isStartOverIntent', () => {
  it('matches the exact prod-reported phrase', () => {
    expect(isStartOverIntent('I want to start from scratch')).toBe(true)
  })

  it('matches common rephrasings', () => {
    expect(isStartOverIntent('can we start over?')).toBe(true)
    expect(isStartOverIntent('lets start again')).toBe(true)
    expect(isStartOverIntent('start fresh please')).toBe(true)
    expect(isStartOverIntent('forget this trip')).toBe(true)
    expect(isStartOverIntent('scrap this trip')).toBe(true)
    expect(isStartOverIntent('reset everything')).toBe(true)
    expect(isStartOverIntent('I want to plan a completely new trip')).toBe(true)
    expect(isStartOverIntent('planning a different trip now')).toBe(true)
  })

  it('is case-insensitive', () => {
    expect(isStartOverIntent('START OVER')).toBe(true)
  })

  it('does not match normal wizard answers', () => {
    expect(isStartOverIntent('Bali, Indonesia')).toBe(false)
    expect(isStartOverIntent('yes please')).toBe(false)
    expect(isStartOverIntent('a relaxed honeymoon for 5 days')).toBe(false)
  })

  it('does not fire on a long unrelated message containing similar words', () => {
    const longMessage =
      'I was thinking we could start fresh ideas about the itinerary but honestly ' +
      'just keep the current destination and dates, only change the budget and pace ' +
      'and maybe add a new activity or two around day three'
    expect(isStartOverIntent(longMessage)).toBe(false)
  })

  it('is empty/whitespace safe', () => {
    expect(isStartOverIntent('')).toBe(false)
    expect(isStartOverIntent('   ')).toBe(false)
  })
})
