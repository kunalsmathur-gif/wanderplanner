import * as React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import ItineraryPage from '@/app/itinerary/page'
import { useAppStore } from '@/store/appStore'
import { useAuthStore } from '@/store/authStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { loadLastItinerary } from '@/lib/resumeLastItinerary'

const replace = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
}))

// The three-column dashboard, wizard, chat panel and floating button pull in
// a large subtree (map, chat, etc.) that isn't relevant here — this test is
// about the page's hydration/redirect/resume gate, not what it renders once
// past it, so each is swapped for a cheap marker.
vi.mock('@/components/layout/ThreeColumnLayout', () => ({
  ThreeColumnLayout: () => <div data-testid="three-column-layout" />,
}))
vi.mock('@/components/wizard/LLMWizard', () => ({
  LLMWizard: () => <div data-testid="llm-wizard" />,
}))
vi.mock('@/components/common/FloatingAnyaButton', () => ({
  FloatingAnyaButton: () => <div data-testid="floating-anya-button" />,
}))
vi.mock('@/components/chat/ChatPanel', () => ({
  ChatPanel: () => <div data-testid="chat-panel" />,
}))

vi.mock('@/lib/resumeLastItinerary', () => ({
  loadLastItinerary: vi.fn(),
}))

const initialAppState = useAppStore.getState()
const initialAuthState = useAuthStore.getState()
const initialItineraryState = useItineraryStore.getState()

const SAVED_DAYS = [
  { day_number: 1, date: '2026-09-01', theme: 'Arrival', items: [], transit_warnings: [] },
]

function signIn() {
  useAuthStore.setState({
    ...initialAuthState,
    status: 'authenticated',
    user: {
      id: 'user-1',
      email: 'ada@example.com',
      display_name: 'Ada',
      is_admin: false,
      auth_provider: 'password',
    },
  })
}

function signOut() {
  useAuthStore.setState({ ...initialAuthState, status: 'unauthenticated', user: null })
}

describe('ItineraryPage — empty-state gate', () => {
  beforeEach(() => {
    replace.mockReset()
    vi.mocked(loadLastItinerary).mockReset()
  })

  afterEach(() => {
    useAppStore.setState(initialAppState)
    useAuthStore.setState(initialAuthState)
    useItineraryStore.setState(initialItineraryState)
  })

  it('renders the dashboard (no redirect) once a saved itinerary has hydrated', async () => {
    useItineraryStore.setState({ days: SAVED_DAYS })
    signIn()

    render(<ItineraryPage />)

    expect(await screen.findByTestId('three-column-layout')).toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })

  it('redirects a signed-out visitor with no saved itinerary to the landing page', async () => {
    signOut()

    render(<ItineraryPage />)

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/'))
    expect(loadLastItinerary).not.toHaveBeenCalled()
  })

  it('does not redirect while auth is still resolving, only once it settles', async () => {
    useAuthStore.setState({ ...initialAuthState, status: 'loading', user: null })

    render(<ItineraryPage />)

    // Give pending effects/microtasks a chance to run — a premature redirect
    // would show up here.
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(replace).not.toHaveBeenCalled()

    signOut()
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/'))
  })

  it('re-fetches from the server for a signed-in user instead of bouncing away, and does not redirect when it succeeds', async () => {
    signIn()
    vi.mocked(loadLastItinerary).mockImplementation(async () => {
      // Mirrors what the real implementation does: repopulate the store
      // from the server-side saved trip.
      useItineraryStore.setState({ days: SAVED_DAYS })
      return { destination: 'Kyoto' }
    })

    render(<ItineraryPage />)

    await waitFor(() => expect(loadLastItinerary).toHaveBeenCalled())
    expect(await screen.findByTestId('three-column-layout')).toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })

  it('falls back to /account (not /) for a signed-in user whose re-fetch also comes back empty', async () => {
    signIn()
    vi.mocked(loadLastItinerary).mockResolvedValue(null)

    render(<ItineraryPage />)

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/account'))
  })
})
