import { create } from 'zustand'

export type FeedbackPromptTrigger = 'back' | 'generate' | 'book' | 'share'

// Controls the dismissible feedback popup (TripFeedbackPopup) that surfaces
// on key "leaving/acting on this itinerary" moments — Edit Trip (back to
// the wizard), Generate/regenerate, Get Quotation (book via local expert),
// and Share. `hasInteracted` latches true the first time the user either
// submits a vote or dismisses the popup, so we ask at most once per
// itinerary session rather than nagging on every subsequent trigger.
interface FeedbackPromptStore {
  open: boolean
  trigger: FeedbackPromptTrigger | null
  hasInteracted: boolean
  request: (trigger: FeedbackPromptTrigger) => void
  dismiss: () => void
  markInteracted: () => void
  resetForNewItinerary: () => void
}

export const useFeedbackPromptStore = create<FeedbackPromptStore>((set, get) => ({
  open: false,
  trigger: null,
  hasInteracted: false,
  request: (trigger) => {
    if (get().hasInteracted || get().open) return
    set({ open: true, trigger })
  },
  dismiss: () => set({ open: false, hasInteracted: true }),
  markInteracted: () => set({ open: false, hasInteracted: true }),
  // Called after a fresh generation completes, so a new itinerary gets its
  // own feedback opportunity instead of inheriting the prior one's "already
  // asked" state.
  resetForNewItinerary: () => set({ hasInteracted: false, open: false, trigger: null }),
}))
