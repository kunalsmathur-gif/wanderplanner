import { describe, it, expect, beforeEach } from 'vitest'
import { act } from 'react'
import { useTripConfigStore } from '@/store/tripConfigStore'

// Reset store before each test to avoid state leaking between tests
beforeEach(() => {
  act(() => {
    useTripConfigStore.getState().resetConfig()
  })
})

describe('tripConfigStore', () => {
  describe('effectivePace()', () => {
    it('returns the user-set pace when no kids are present', () => {
      act(() => {
        useTripConfigStore.getState().updateConfig({ pace: 'packed' })
        useTripConfigStore.getState().updateGroup({ kids: [] })
      })
      expect(useTripConfigStore.getState().effectivePace()).toBe('packed')
    })

    it('returns relaxed when any kid is under 5 years old', () => {
      act(() => {
        useTripConfigStore.getState().updateConfig({ pace: 'packed' })
        useTripConfigStore.getState().updateGroup({ kids: [{ age: 3 }] })
      })
      expect(useTripConfigStore.getState().effectivePace()).toBe('relaxed')
    })

    it('returns relaxed for a kid exactly aged 4', () => {
      act(() => {
        useTripConfigStore.getState().updateGroup({ kids: [{ age: 4 }] })
        useTripConfigStore.getState().updateConfig({ pace: 'moderate' })
      })
      expect(useTripConfigStore.getState().effectivePace()).toBe('relaxed')
    })

    it('does NOT override to relaxed when youngest kid is exactly 5', () => {
      act(() => {
        useTripConfigStore.getState().updateGroup({ kids: [{ age: 5 }] })
        useTripConfigStore.getState().updateConfig({ pace: 'moderate' })
      })
      expect(useTripConfigStore.getState().effectivePace()).toBe('moderate')
    })

    it('returns relaxed if at least one kid is under 5 even when others are older', () => {
      act(() => {
        useTripConfigStore.getState().updateGroup({ kids: [{ age: 7 }, { age: 2 }] })
        useTripConfigStore.getState().updateConfig({ pace: 'moderate' })
      })
      expect(useTripConfigStore.getState().effectivePace()).toBe('relaxed')
    })
  })

  describe('updateGroup()', () => {
    it('merges partial group updates without losing other fields', () => {
      act(() => {
        useTripConfigStore.getState().updateGroup({ adults: 3, seniors: 1 })
      })
      const { group } = useTripConfigStore.getState().config
      expect(group.adults).toBe(3)
      expect(group.seniors).toBe(1)
      expect(group.infants).toBe(0) // default preserved
    })
  })

  describe('setDestination()', () => {
    it('sets destination correctly', () => {
      act(() => {
        useTripConfigStore.getState().setDestination({ city: 'Tokyo', country: 'JP', lat: 35.6, lon: 139.6 })
      })
      expect(useTripConfigStore.getState().config.destination?.city).toBe('Tokyo')
    })

    it('clears destination when passed null', () => {
      act(() => {
        useTripConfigStore.getState().setDestination({ city: 'Tokyo', country: 'JP', lat: 35.6, lon: 139.6 })
        useTripConfigStore.getState().setDestination(null)
      })
      expect(useTripConfigStore.getState().config.destination).toBeNull()
    })
  })

  describe('resetConfig()', () => {
    it('resets all fields to defaults', () => {
      act(() => {
        useTripConfigStore.getState().updateConfig({ purpose: 'adventure', pace: 'packed' })
        useTripConfigStore.getState().updateGroup({ adults: 5 })
        useTripConfigStore.getState().resetConfig()
      })
      const { config } = useTripConfigStore.getState()
      expect(config.purpose).toBe('')
      expect(config.pace).toBe('moderate')
      expect(config.group.adults).toBe(1)
    })
  })
})
