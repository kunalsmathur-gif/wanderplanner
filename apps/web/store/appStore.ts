import { create } from 'zustand'

export type AppStep = 1 | 2 | 3
export type Step3View = 'itinerary' | 'comparison'

interface AppStore {
  step: AppStep
  step3View: Step3View
  goToStep: (step: AppStep) => void
  goBack: () => void
  setStep3View: (view: Step3View) => void
}

export const useAppStore = create<AppStore>((set, get) => ({
  step: 1,
  step3View: 'itinerary',
  goToStep: (step) => set({ step }),
  goBack: () => {
    const { step } = get()
    if (step > 1) set({ step: (step - 1) as AppStep })
  },
  setStep3View: (step3View) => set({ step3View }),
}))
