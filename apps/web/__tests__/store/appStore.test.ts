import { describe, it, expect, beforeEach } from 'vitest'
import { act } from 'react'
import { useAppStore } from '@/store/appStore'

beforeEach(() => {
  act(() => {
    useAppStore.getState().openWizard()
    useAppStore.getState().setStep3View('itinerary')
  })
})

describe('appStore', () => {
  describe('wizard visibility', () => {
    it('opens the wizard', () => {
      act(() => { useAppStore.getState().openWizard() })
      expect(useAppStore.getState().wizardOpen).toBe(true)
    })

    it('closes the wizard', () => {
      act(() => { useAppStore.getState().closeWizard() })
      expect(useAppStore.getState().wizardOpen).toBe(false)
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
