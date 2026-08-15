import * as React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatPanel } from '@/components/chat/ChatPanel'
import { useChatStore } from '@/store/chatStore'
import { useAuthStore } from '@/store/authStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { loadLastItinerary } from '@/lib/resumeLastItinerary'

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
}))

const initialAuthState = useAuthStore.getState()
const initialChatState = useChatStore.getState()
const initialTripConfigState = useTripConfigStore.getState()

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

describe('ChatPanel — resume last itinerary intent (issue #65)', () => {
  beforeEach(() => {
    useChatStore.setState({ ...initialChatState, isOpen: true })
    vi.mocked(loadLastItinerary).mockReset()
  })

  afterEach(() => {
    useAuthStore.setState(initialAuthState)
    useChatStore.setState(initialChatState)
    useTripConfigStore.setState(initialTripConfigState)
  })

  it('loads the saved trip and confirms it when a signed-in user asks to see their last itinerary', async () => {
    signIn()
    vi.mocked(loadLastItinerary).mockResolvedValue({ destination: 'Kyoto' })

    render(<ChatPanel />)
    await sendMessage('show me my last itinerary')

    await waitFor(() => expect(loadLastItinerary).toHaveBeenCalled())
    expect(await screen.findByText(/Kyoto/)).toBeInTheDocument()
  })

  it('tells the user there is nothing saved yet when none exists', async () => {
    signIn()
    vi.mocked(loadLastItinerary).mockResolvedValue(null)

    render(<ChatPanel />)
    await sendMessage('continue my last trip')

    expect(await screen.findByText(/don't have a saved trip/i)).toBeInTheDocument()
  })

  it('never calls loadLastItinerary for a guest, even with matching phrasing', async () => {
    useAuthStore.setState({ ...initialAuthState, status: 'unauthenticated', user: null })

    render(<ChatPanel />)
    await sendMessage('show me my last itinerary')

    // Falls through to the normal chatRefine path instead — no resume attempt leaks to a guest.
    await waitFor(() => expect(loadLastItinerary).not.toHaveBeenCalled())
  })
})
