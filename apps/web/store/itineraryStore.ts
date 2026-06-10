import { create } from 'zustand'
import type { ItineraryDay, ItineraryResponse } from '@/types'

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

  setDays: (days: ItineraryDay[], score: number) => void
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

  setDays: (days, score) => set({ days, alignmentScore: score, status: 'success' }),
  setActiveDay: (activeDay) => set({ activeDay }),
  setHoveredItem: (hoveredItemId) => set({ hoveredItemId }),
  setStatus: (status) => set({ status }),
  setProgress: (progress) => set({ progress }),
  setError: (error) => set({ error, status: 'error' }),
  reset: () => set({
    days: [], activeDay: 0, hoveredItemId: null,
    status: 'idle', progress: { message: '', step: 0, total: 4 },
    error: null, alignmentScore: 0,
  }),
}))
