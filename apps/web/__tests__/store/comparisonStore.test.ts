import { describe, it, expect, beforeEach } from 'vitest'
import { act } from 'react'
import { useComparisonStore } from '@/store/comparisonStore'
import type { ComparisonResponse, DestinationInput } from '@/types'

const DEST_A: DestinationInput = { city: 'Tokyo', country: 'JP', lat: 35.6, lon: 139.6 }
const DEST_B: DestinationInput = { city: 'Paris', country: 'FR', lat: 48.8, lon: 2.3 }

const FULL_RESULT: ComparisonResponse = {
  comparison: [
    { parameter: 'Weather', unit: '°C', values: { Tokyo: 22, Paris: 18 }, winner: 'Tokyo', highlight: '' },
    { parameter: 'Budget', unit: 'USD/day', values: { Tokyo: 120, Paris: 95 }, winner: 'Paris', highlight: '' },
  ],
  partial_failures: [],
}

const PARTIAL_RESULT: ComparisonResponse = {
  ...FULL_RESULT,
  partial_failures: ['visa'],
}

beforeEach(() => {
  act(() => { useComparisonStore.getState().reset() })
})

describe('comparisonStore', () => {
  it('starts in idle state', () => {
    expect(useComparisonStore.getState().status).toBe('idle')
    expect(useComparisonStore.getState().result).toBeNull()
  })

  it('sets destinations correctly', () => {
    act(() => { useComparisonStore.getState().setDestinations(DEST_A, DEST_B) })
    expect(useComparisonStore.getState().destinationA?.city).toBe('Tokyo')
    expect(useComparisonStore.getState().destinationB?.city).toBe('Paris')
  })

  it('sets status to success when result has no partial failures', () => {
    act(() => { useComparisonStore.getState().setResult(FULL_RESULT) })
    expect(useComparisonStore.getState().status).toBe('success')
  })

  it('sets status to partial when result has partial failures', () => {
    act(() => { useComparisonStore.getState().setResult(PARTIAL_RESULT) })
    expect(useComparisonStore.getState().status).toBe('partial')
  })

  it('stores result data correctly', () => {
    act(() => { useComparisonStore.getState().setResult(FULL_RESULT) })
    expect(useComparisonStore.getState().result?.comparison).toHaveLength(2)
  })

  it('reset() clears all state', () => {
    act(() => {
      useComparisonStore.getState().setDestinations(DEST_A, DEST_B)
      useComparisonStore.getState().setResult(FULL_RESULT)
      useComparisonStore.getState().reset()
    })
    const s = useComparisonStore.getState()
    expect(s.status).toBe('idle')
    expect(s.result).toBeNull()
    expect(s.destinationA).toBeNull()
  })

  it('setStatus() can set loading', () => {
    act(() => { useComparisonStore.getState().setStatus('loading') })
    expect(useComparisonStore.getState().status).toBe('loading')
  })
})
