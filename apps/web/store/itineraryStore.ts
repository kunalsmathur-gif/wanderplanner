import { create } from 'zustand'
import type { ItineraryDay, ExpenseBreakdown, GenerationTier } from '@/types'
import { useItineraryFeedbackStore } from '@/store/itineraryFeedbackStore'
import { useFeedbackPromptStore } from '@/store/feedbackPromptStore'

type GenerationStatus = 'idle' | 'loading' | 'success' | 'error'

interface GenerationProgress {
  message: string
  step: number
  total: number
}

interface GenerationError {
  code: string
  message: string
  retryable: boolean
}

interface ItineraryStore {
  days: ItineraryDay[]
  activeDay: number
  hoveredItemId: string | null
  status: GenerationStatus
  progress: GenerationProgress
  error: GenerationError | null
  alignmentScore: number
  expenseBreakdown: ExpenseBreakdown | null
  generationTier: GenerationTier

  setDays: (
    days: ItineraryDay[],
    score: number,
    breakdown?: ExpenseBreakdown,
    generationTier?: GenerationTier,
  ) => void
  setActiveDay: (day: number) => void
  setHoveredItem: (id: string | null) => void
  setStatus: (status: GenerationStatus) => void
  setProgress: (progress: GenerationProgress) => void
  setError: (error: GenerationError | null) => void
  reset: () => void
}

export const useItineraryStore = create<ItineraryStore>((set) => ({
  days: [],
  activeDay: 0,
  hoveredItemId: null,
  status: 'idle',
  progress: { message: '', step: 0, total: 4 },
  error: null,
  alignmentScore: 0,
  expenseBreakdown: null,
  generationTier: 'live',

  setDays: (days, score, breakdown, generationTier) => {
    // A fresh itinerary deserves its own feedback opportunity — clear any
    // vote/prompt state left over from the previous one so the widget/popup
    // don't show a stale "already answered" state for a plan the user
    // hasn't actually reacted to yet.
    useItineraryFeedbackStore.getState().reset()
    useFeedbackPromptStore.getState().resetForNewItinerary()
    set({
      days,
      alignmentScore: score,
      status: 'success',
      expenseBreakdown: breakdown ?? null,
      generationTier: generationTier ?? 'live',
    })
  },
  setActiveDay: (activeDay) => set({ activeDay }),
  setHoveredItem: (hoveredItemId) => set({ hoveredItemId }),
  setStatus: (status) => set({ status }),
  setProgress: (progress) => set({ progress }),
  setError: (error) => set({ error, status: 'error' }),
  reset: () => set({
    days: [], activeDay: 0, hoveredItemId: null,
    status: 'idle', progress: { message: '', step: 0, total: 4 },
    error: null, alignmentScore: 0, expenseBreakdown: null, generationTier: 'live',
  }),
}))
