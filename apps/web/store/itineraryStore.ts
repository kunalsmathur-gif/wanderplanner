import { create } from 'zustand'
import type { ItineraryDay, ExpenseBreakdown, GenerationTier } from '@/types'

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

  setDays: (days, score, breakdown, generationTier) =>
    set({
      days,
      alignmentScore: score,
      status: 'success',
      expenseBreakdown: breakdown ?? null,
      generationTier: generationTier ?? 'live',
    }),
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
