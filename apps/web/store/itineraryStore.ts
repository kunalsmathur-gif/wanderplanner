import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
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
  warnings: string[]
  // Correlates this generation to the implicit-quality-signal endpoint
  // (POST /api/generation-signal) — undefined when the backend didn't store
  // this generation in the RAG corpus.
  generationId: string | undefined
  // When this itinerary was first shown, so the session-duration signal can
  // be computed as "now - generatedAt" on unmount/navigation-away.
  generatedAt: number | null

  setDays: (
    days: ItineraryDay[],
    score: number,
    breakdown?: ExpenseBreakdown,
    generationTier?: GenerationTier,
    warnings?: string[],
    generationId?: string,
  ) => void
  setActiveDay: (day: number) => void
  setHoveredItem: (id: string | null) => void
  setStatus: (status: GenerationStatus) => void
  setProgress: (progress: GenerationProgress) => void
  setError: (error: GenerationError | null) => void
  reset: () => void
}

/**
 * Persisted to **sessionStorage**, not localStorage, and deliberately so.
 *
 * The itinerary now lives at its own `/itinerary` route, so a refresh or a
 * direct link has to be able to restore it — without persistence the route
 * would bounce to the landing page every time, which is worse than no route
 * at all. sessionStorage scopes that to the one tab and clears itself when
 * the tab closes, so a generated trip does not outlive the browsing session
 * on a shared machine. `useAuthStore.logout()` clears it explicitly too.
 *
 * Only the itinerary content is persisted — `status`, `progress` and `error`
 * describe an in-flight generation and would otherwise be restored as a
 * permanently "loading" or "failed" screen after a refresh.
 */
export const useItineraryStore = create<ItineraryStore>()(persist((set) => ({
  days: [],
  activeDay: 0,
  hoveredItemId: null,
  status: 'idle',
  progress: { message: '', step: 0, total: 4 },
  error: null,
  alignmentScore: 0,
  expenseBreakdown: null,
  generationTier: 'live',
  warnings: [],
  generationId: undefined,
  generatedAt: null,

  setDays: (days, score, breakdown, generationTier, warnings, generationId) => {
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
      warnings: warnings ?? [],
      generationId,
      generatedAt: Date.now(),
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
    warnings: [], generationId: undefined, generatedAt: null,
  }),
}), {
  name: 'wanderplanner-itinerary',
  storage: createJSONStorage(() => sessionStorage),
  partialize: (state) => ({
    days: state.days,
    activeDay: state.activeDay,
    alignmentScore: state.alignmentScore,
    expenseBreakdown: state.expenseBreakdown,
    generationTier: state.generationTier,
    warnings: state.warnings,
    generationId: state.generationId,
    generatedAt: state.generatedAt,
    // A restored itinerary is a finished one; without this the route guard
    // would see days but a stale 'idle' status.
    status: 'success' as const,
  }),
}))
