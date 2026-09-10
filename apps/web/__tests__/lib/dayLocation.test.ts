import { describe, expect, it } from 'vitest'
import { resolveDayCity } from '@/lib/dayLocation'
import type { DestinationInput, ItineraryDay, ItineraryItem } from '@/types'

function item(lat: number, lon: number): ItineraryItem {
  return {
    id: 'x',
    time_start: '09:00',
    time_end: '10:00',
    title: 'Stop',
    description: '',
    location: { lat, lon, address: '' },
    tags: [],
    booking_url: '',
    youtube_video_id: '',
    alignment_score: 0,
    warnings: [],
  }
}

function day(items: ItineraryItem[]): ItineraryDay {
  return { day_number: 1, date: '2026-12-01', theme: '', items, transit_warnings: [] }
}

const COLOMBO: DestinationInput = { city: 'Colombo', country: 'Sri Lanka', lat: 6.9271, lon: 79.8612 }
const MIRISSA: DestinationInput = { city: 'Mirissa', country: 'Sri Lanka', lat: 5.9483, lon: 80.4589 }
const YALA: DestinationInput = { city: 'Yala', country: 'Sri Lanka', lat: 6.3728, lon: 81.5183 }
const BENTOTA: DestinationInput = { city: 'Bentota', country: 'Sri Lanka', lat: 6.4260, lon: 79.9955 }

describe('resolveDayCity', () => {
  it('matches a day to the nearest of destination + hops, not always the main destination', () => {
    // 🔴 Reported live 2026-09-10: a Bentota day's tips/best-time panel
    // showed Colombo (the trip's top-level `destination`) because the old
    // logic never looked at the day's own item coordinates at all.
    const bentotaDay = day([item(6.42, 79.99)])
    const result = resolveDayCity(bentotaDay, COLOMBO, [MIRISSA, YALA, BENTOTA])
    expect(result?.city).toBe('Bentota')
  })

  it('picks a different stop for a different day of the same trip', () => {
    const mirissaDay = day([item(5.95, 80.46)])
    const result = resolveDayCity(mirissaDay, COLOMBO, [MIRISSA, YALA, BENTOTA])
    expect(result?.city).toBe('Mirissa')
  })

  it('averages multiple items in the day before matching', () => {
    // Two items both near Yala should still resolve to Yala even though
    // neither is an exact coordinate match.
    const yalaDay = day([item(6.37, 81.5), item(6.38, 81.52)])
    const result = resolveDayCity(yalaDay, COLOMBO, [MIRISSA, YALA, BENTOTA])
    expect(result?.city).toBe('Yala')
  })

  it('falls back to the main destination when the day has no located items', () => {
    const emptyDay = day([])
    const result = resolveDayCity(emptyDay, COLOMBO, [MIRISSA, YALA])
    expect(result?.city).toBe('Colombo')
  })

  it('falls back to the main destination when there are no hops at all', () => {
    const someDay = day([item(6.42, 79.99)]) // Bentota coords, but no hops defined
    const result = resolveDayCity(someDay, COLOMBO, [])
    expect(result?.city).toBe('Colombo')
  })

  it('returns null when neither destination nor hops are geocoded', () => {
    const someDay = day([item(6.42, 79.99)])
    const result = resolveDayCity(someDay, null, [])
    expect(result).toBeNull()
  })

  it('handles a missing day (index out of range) gracefully', () => {
    const result = resolveDayCity(undefined, COLOMBO, [MIRISSA])
    expect(result?.city).toBe('Colombo')
  })
})
