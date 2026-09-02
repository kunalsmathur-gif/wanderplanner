import * as React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatPanel } from '@/components/chat/ChatPanel'
import { useChatStore } from '@/store/chatStore'
import { useAuthStore } from '@/store/authStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { chatRefine, checkFeasibility, streamItinerary, sendGenerationSignal } from '@/lib/api'
import type { ItineraryResponse } from '@/types'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/lib/resumeLastItinerary', () => ({
  loadLastItinerary: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  chatRefine: vi.fn(),
  streamItinerary: vi.fn(),
  checkFeasibility: vi.fn(),
  sendGenerationSignal: vi.fn(),
}))

const initialAuthState = useAuthStore.getState()
const initialChatState = useChatStore.getState()
const initialTripConfigState = useTripConfigStore.getState()
const initialItineraryState = useItineraryStore.getState()

function signIn() {
  useAuthStore.setState({
    ...initialAuthState,
    status: 'authenticated',
    user: {
      id: 'user-1', email: 'ada@example.com', display_name: 'Ada',
      is_admin: false, auth_provider: 'password',
    },
  })
}

async function sendMessage(text: string) {
  const user = userEvent.setup()
  const textbox = screen.getByRole('textbox')
  await user.type(textbox, text)
  await user.keyboard('{Enter}')
}

const NEW_RESULT: ItineraryResponse = {
  days: [{ day_number: 1, date: '2026-01-01', theme: 'Arrival', items: [], transit_warnings: [] }],
  alignment_score: 90,
  warnings: [],
  expense_breakdown: {} as ItineraryResponse['expense_breakdown'],
  generation_id: 'gen-new',
}

// Regression guard for a live prod bug (2026-09-02): a "regenerate" reply
// asked the user to confirm, the user typed "is it done?" instead of
// clicking "Yes, rebuild it", and the model claimed it was "now
// regenerating" while nothing had actually been triggered — no loader
// appeared, no itinerary changed. Typing a plain confirmation ("yes", "go
// ahead", etc.) while a regeneration is pending must trigger the real
// regeneration exactly like clicking the button would.
describe('ChatPanel — typed confirmation triggers pending regeneration', () => {
  beforeEach(() => {
    useChatStore.setState({ ...initialChatState, isOpen: true })
    useItineraryStore.setState({
      ...initialItineraryState,
      days: [{ day_number: 1, date: '2026-01-01', theme: 'Arrival', items: [], transit_warnings: [] }],
      generationId: 'gen-old',
      generatedAt: Date.now(),
    })
    signIn()
    vi.mocked(sendGenerationSignal).mockClear()
    vi.mocked(checkFeasibility).mockResolvedValue({
      feasible: true,
      destination_verified: true,
    } as never)
  })

  afterEach(() => {
    useAuthStore.setState(initialAuthState)
    useChatStore.setState(initialChatState)
    useTripConfigStore.setState(initialTripConfigState)
    useItineraryStore.setState(initialItineraryState)
  })

  it('triggers regeneration when the user types "yes" instead of clicking the confirm button', async () => {
    vi.mocked(chatRefine).mockResolvedValue({
      reply: "I'll regenerate your itinerary so whale watching and Yala are on different days. Shall I proceed?",
      action_type: 'regenerate',
      major_change: true,
      config_patch: { pace: 'relaxed' },
    } as never)
    vi.mocked(streamItinerary).mockImplementation((_config, _onStatus, onData) => {
      onData(NEW_RESULT)
      return () => {}
    })

    render(<ChatPanel />)
    await sendMessage('split whale watching and yala across different days')

    // Confirmation card appears instead of auto-triggering.
    await screen.findByText(/will regenerate your itinerary/i)
    expect(streamItinerary).not.toHaveBeenCalled()

    await sendMessage('yes')

    await waitFor(() => expect(streamItinerary).toHaveBeenCalled())
    expect(useItineraryStore.getState().generationId).toBe('gen-new')
    // The typed "yes" must not be sent to chatRefine as a fresh turn — it's
    // intercepted client-side as a confirmation, not routed through the LLM.
    expect(chatRefine).toHaveBeenCalledTimes(1)
  })
})
