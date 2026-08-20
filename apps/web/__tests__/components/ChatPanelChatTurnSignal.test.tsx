import * as React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatPanel } from '@/components/chat/ChatPanel'
import { useChatStore } from '@/store/chatStore'
import { useAuthStore } from '@/store/authStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { chatRefine, sendGenerationSignal } from '@/lib/api'

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

async function sendMessage(text: string) {
  const user = userEvent.setup()
  const textbox = screen.getByRole('textbox')
  await user.type(textbox, text)
  await user.keyboard('{Enter}')
}

describe('ChatPanel — chat_turn signal (issue #34)', () => {
  beforeEach(() => {
    useChatStore.setState({ ...initialChatState, isOpen: true })
    useAuthStore.setState({
      ...initialAuthState,
      status: 'authenticated',
      user: {
        id: 'user-1', email: 'ada@example.com', display_name: 'Ada',
        is_admin: false, auth_provider: 'password',
      },
    })
    vi.mocked(sendGenerationSignal).mockClear()
    vi.mocked(chatRefine).mockResolvedValue({
      reply: 'Sure thing!',
      action_type: 'none',
    } as never)
  })

  afterEach(() => {
    useAuthStore.setState(initialAuthState)
    useChatStore.setState(initialChatState)
    useTripConfigStore.setState(initialTripConfigState)
    useItineraryStore.setState(initialItineraryState)
  })

  it('reports a chat_turn against the current generation once an itinerary exists', async () => {
    useItineraryStore.setState({
      ...initialItineraryState,
      days: [{ day_number: 1, date: '2026-01-01', theme: 'Arrival', items: [], transit_warnings: [] }],
      generationId: 'gen-1',
      generatedAt: Date.now(),
    })

    render(<ChatPanel />)
    await sendMessage('what should I pack?')

    await waitFor(() => expect(chatRefine).toHaveBeenCalled())
    expect(sendGenerationSignal).toHaveBeenCalledWith('gen-1', 'chat_turn')
  })

  it('does not report a chat_turn before any itinerary has been generated', async () => {
    useItineraryStore.setState({ ...initialItineraryState, days: [], generationId: undefined, generatedAt: null })

    render(<ChatPanel />)
    await sendMessage('what should I pack?')

    await waitFor(() => expect(chatRefine).toHaveBeenCalled())
    expect(sendGenerationSignal).not.toHaveBeenCalled()
  })
})
