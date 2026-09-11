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
import type { FeasibilityResponse } from '@/types'

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

describe('ChatPanel — day-cost-preference regeneration (2026-09-11 bug reports)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useChatStore.setState({ ...initialChatState, isOpen: true })
    useItineraryStore.setState({
      ...initialItineraryState,
      days: [{ day_number: 1, date: '2026-01-01', theme: 'Arrival', items: [], transit_warnings: [] }],
      generationId: 'gen-old',
      generatedAt: Date.now(),
    })
    signIn()
  })

  afterEach(() => {
    useAuthStore.setState(initialAuthState)
    useChatStore.setState(initialChatState)
    useTripConfigStore.setState(initialTripConfigState)
    useItineraryStore.setState(initialItineraryState)
  })

  it('shows a visible "checking your budget" note while the feasibility check is in flight, not silence', async () => {
    // 🔴 Found live 2026-09-11: the canned "Done — rebuilding now" reply for
    // a day-cost-preference edit was followed by total silence while
    // checkFeasibility() ran, so the user assumed nothing had happened and
    // sent a confused follow-up message before the check resolved.
    vi.mocked(chatRefine).mockResolvedValue({
      reply: 'Done — I\'m making day 1 lighter on the wallet and rebuilding your itinerary now.',
      action_type: 'patch_config',
      major_change: false,
      config_patch: { day_cost_preferences: [{ day_number: 1, direction: 'cheaper' }] },
    } as never)
    let resolveFeasibility: (v: FeasibilityResponse) => void = () => {}
    vi.mocked(checkFeasibility).mockReturnValue(
      new Promise((resolve) => { resolveFeasibility = resolve }) as never,
    )

    render(<ChatPanel />)
    await sendMessage('reduce budget for day 1')

    await waitFor(() => expect(checkFeasibility).toHaveBeenCalled())
    expect(await screen.findByText(/checking your budget/i)).toBeInTheDocument()

    resolveFeasibility({ feasible: true, destination_verified: true } as never)
    await waitFor(() => expect(screen.queryByText(/checking your budget/i)).not.toBeInTheDocument())
  })

  it('acknowledges the applied day-cost edit before an infeasible-budget verdict, instead of reading as a contradiction', async () => {
    // 🔴 Found live 2026-09-11: a user asked to make a day cheaper and was
    // then told to increase their overall budget with no acknowledgment of
    // the edit they'd just made — reading as if the request was ignored.
    vi.mocked(chatRefine).mockResolvedValue({
      reply: 'Done — I\'m making day 1 lighter on the wallet and rebuilding your itinerary now.',
      action_type: 'patch_config',
      major_change: false,
      config_patch: { day_cost_preferences: [{ day_number: 1, direction: 'cheaper' }] },
    } as never)
    vi.mocked(checkFeasibility).mockResolvedValue({
      feasible: false,
      destination_verified: true,
      verdict: 'Budget may be short by ₹38,600.',
      budget_inr: 209426,
      shortfall_inr: 38600,
      buffer_inr: 0,
      bare_minimum_inr: 248026,
      alternatives: [],
      disclaimer: '',
      breakdown: {
        flights_inr: 20000,
        visa_inr: 1826,
        accommodation_inr: 130500,
        daily_expenses_inr: 95700,
        total_estimated_inr: 248026,
      },
    } as never)

    render(<ChatPanel />)
    await sendMessage('reduce budget for day 1')

    const verdictMessage = await screen.findByText(/budget may be short/i)
    expect(verdictMessage.textContent).toMatch(/applied that day 1 change/i)
    expect(streamItinerary).not.toHaveBeenCalled()
  })
})
