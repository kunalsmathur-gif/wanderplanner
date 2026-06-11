import { describe, it, expect, beforeEach } from 'vitest'
import { act } from 'react'
import { useAppStore } from '@/store/appStore'

beforeEach(() => {
  act(() => {
    useAppStore.getState().goToStep(1)
    useAppStore.getState().setStep3View('itinerary')
  })
})

describe('appStore', () => {
  describe('goToStep()', () => {
    it('navigates to step 2', () => {
      act(() => { useAppStore.getState().goToStep(2) })
      expect(useAppStore.getState().step).toBe(2)
    })

    it('navigates to step 3', () => {
      act(() => { useAppStore.getState().goToStep(3) })
      expect(useAppStore.getState().step).toBe(3)
    })
  })

  describe('goBack()', () => {
    it('decrements step from 3 to 2', () => {
      act(() => {
        useAppStore.getState().goToStep(3)
        useAppStore.getState().goBack()
      })
      expect(useAppStore.getState().step).toBe(2)
    })

    it('decrements step from 2 to 1', () => {
      act(() => {
        useAppStore.getState().goToStep(2)
        useAppStore.getState().goBack()
      })
      expect(useAppStore.getState().step).toBe(1)
    })

    it('does not go below step 1', () => {
      act(() => {
        useAppStore.getState().goToStep(1)
        useAppStore.getState().goBack()
      })
      expect(useAppStore.getState().step).toBe(1)
    })
  })

  describe('setStep3View()', () => {
    it('switches to comparison view', () => {
      act(() => { useAppStore.getState().setStep3View('comparison') })
      expect(useAppStore.getState().step3View).toBe('comparison')
    })

    it('switches back to itinerary view', () => {
      act(() => {
        useAppStore.getState().setStep3View('comparison')
        useAppStore.getState().setStep3View('itinerary')
      })
      expect(useAppStore.getState().step3View).toBe('itinerary')
    })
  })
})
