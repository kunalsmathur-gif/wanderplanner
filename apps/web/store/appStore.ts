import { create } from 'zustand'

export type Step3View = 'itinerary' | 'comparison' | 'map-full'

export type AppStep = 1 | 2 | 3
type LegacyStep = AppStep

export interface WizardPreload {
  city: string
  country: string
  days: number
  label: string   // full display string, e.g. "Bali, Indonesia"
}

interface AppStore {
  wizardOpen: boolean
  step3View: Step3View
  wizardPreload: WizardPreload | null
  openWizard: () => void
  openWizardWithPreload: (preload: WizardPreload) => void
  clearWizardPreload: () => void
  closeWizard: () => void
  setStep3View: (view: Step3View) => void

  // Legacy compatibility for unused older screens that still type-check.
  step: LegacyStep
  goToStep: (step: LegacyStep) => void
  goBack: () => void
}

export const useAppStore = create<AppStore>((set) => ({
  wizardOpen: false,
  step: 1,
  step3View: 'itinerary',
  wizardPreload: null,
  openWizard: () => set({ wizardOpen: true, step: 1 }),
  openWizardWithPreload: (preload) => set({ wizardOpen: true, step: 1, wizardPreload: preload }),
  clearWizardPreload: () => set({ wizardPreload: null }),
  closeWizard: () => set({ wizardOpen: false, step: 3 }),
  setStep3View: (step3View) => set({ step3View }),
  goToStep: (step) => set({ step, wizardOpen: step !== 3 }),
  goBack: () => set((state) => {
    if (state.step <= 1) return { step: 1, wizardOpen: true }
    const nextStep = (state.step - 1) as LegacyStep
    return { step: nextStep, wizardOpen: nextStep !== 3 }
  }),
}))
