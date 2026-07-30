import { create } from 'zustand'
import { createItineraryFeedback, updateItineraryFeedback, type FeedbackSentiment } from '@/lib/api'

export type ItineraryFeedbackState = 'idle' | 'awaiting_note' | 'loading' | 'sent' | 'error'

// Single source of truth for the itinerary-wide (not per-item) thumbs
// up/down reaction. Shared between the persistent inline widget in the
// centre section (ItineraryFeedbackWidget) and the dismissible prompt
// popup (TripFeedbackPopup) triggered on key navigation actions — both
// read/write the same state so a vote given in one place is reflected
// (and not re-asked) in the other.
interface ItineraryFeedbackStore {
  state: ItineraryFeedbackState
  vote: FeedbackSentiment | null
  feedbackId: string | null
  note: string
  setNote: (note: string) => void
  thumbsUp: (tripConfigSnapshot: Record<string, unknown>) => Promise<void>
  thumbsDown: () => void
  submitNote: (tripConfigSnapshot: Record<string, unknown>) => Promise<void>
  skipNote: (tripConfigSnapshot: Record<string, unknown>) => Promise<void>
  cancelNote: () => void
  retry: () => void
  reset: () => void
}

async function submitSentiment(
  get: () => ItineraryFeedbackStore,
  set: (partial: Partial<ItineraryFeedbackStore>) => void,
  sentiment: FeedbackSentiment,
  note: string | undefined,
  tripConfigSnapshot: Record<string, unknown>,
) {
  set({ state: 'loading' })
  try {
    const { feedbackId } = get()
    if (feedbackId) {
      await updateItineraryFeedback(feedbackId, sentiment)
    } else {
      const result = await createItineraryFeedback({
        trip_config_snapshot: tripConfigSnapshot,
        scope: 'itinerary',
        sentiment,
        note: note?.trim() || undefined,
      })
      set({ feedbackId: result.id })
    }
    set({ vote: sentiment, state: 'sent' })
  } catch {
    set({ state: 'error' })
  }
}

export const useItineraryFeedbackStore = create<ItineraryFeedbackStore>((set, get) => ({
  state: 'idle',
  vote: null,
  feedbackId: null,
  note: '',
  setNote: (note) => set({ note }),
  thumbsUp: (tripConfigSnapshot) => submitSentiment(get, set, 'thumbs_up', undefined, tripConfigSnapshot),
  thumbsDown: () => set({ state: 'awaiting_note' }),
  submitNote: (tripConfigSnapshot) => submitSentiment(get, set, 'thumbs_down', get().note, tripConfigSnapshot),
  skipNote: (tripConfigSnapshot) => submitSentiment(get, set, 'thumbs_down', undefined, tripConfigSnapshot),
  cancelNote: () => set({ state: 'idle' }),
  retry: () => set({ state: 'idle' }),
  reset: () => set({ state: 'idle', vote: null, feedbackId: null, note: '' }),
}))
