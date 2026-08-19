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
  days: [{ day: 1, date: '2026-01-01', title: 'Day 1', items: [] }],
  alignment_score: 90,
  warnings: [],
  expense_breakdown: {} as ItineraryResponse['expense_breakdown'],
  generation_id: 'gen-new',
}

describe('ChatPanel — regenerated signal (issue #34)', () => {
  beforeEach(() => {
    useChatStore.setState({ ...initialChatState, isOpen: true })
    useItineraryStore.setState({
      ...initialItineraryState,
      days: [{ day: 1, date: '2026-01-01', title: 'Day 1', items: [] }],
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

  it('reports the outgoing generation id as "regenerated" before the new plan replaces it', async () => {
    vi.mocked(chatRefine).mockResolvedValue({
      reply: 'Sure, updating!',
      action_type: 'regenerate',
      major_change: true,
      config_patch: { budget_inr: 50000 },
    } as never)
    vi.mocked(streamItinerary).mockImplementation((_config, _onStatus, onData) => {
      onData(NEW_RESULT)
      return () => {}
    })

    render(<ChatPanel />)
    await sendMessage('increase my budget a lot please')

    const confirmButton = await screen.findByRole('button', { name: /confirm|yes|update/i })
    await userEvent.setup().click(confirmButton)

    await waitFor(() => expect(streamItinerary).toHaveBeenCalled())
    expect(sendGenerationSignal).toHaveBeenCalledWith('gen-old', 'regenerated')
    expect(useItineraryStore.getState().generationId).toBe('gen-new')
  })
})
