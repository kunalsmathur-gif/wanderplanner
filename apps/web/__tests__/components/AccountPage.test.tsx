import * as React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AccountPage from '@/app/account/page'
import { useAuthStore } from '@/store/authStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { getLastItinerary } from '@/lib/api'

const push = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('next/link', () => ({
  default: React.forwardRef<HTMLAnchorElement, React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }>(
    ({ href, children, ...props }, ref) => (
      <a ref={ref} href={href} {...props}>
        {children}
      </a>
    )
  ),
}))

vi.mock('@/lib/authApi', () => ({
  deleteMyAccount: vi.fn(),
  authErrorMessage: (err: unknown) => String(err),
}))

vi.mock('@/lib/api', () => ({
  getLastItinerary: vi.fn(),
}))

const initialAuthState = useAuthStore.getState()
const initialTripConfigState = useTripConfigStore.getState()
const initialItineraryState = useItineraryStore.getState()

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

const SAVED_TRIP = {
  trip_config: {
    ...initialTripConfigState.config,
    destination: { city: 'Kyoto', country: 'Japan', lat: 35.0, lon: 135.8 },
    dates: { start: '2026-09-01', end: '2026-09-05', flexible: false },
  },
  itinerary: {
    days: [{ day_number: 1, date: '2026-09-01', theme: 'Arrival', items: [], transit_warnings: [] }],
    alignment_score: 0.9,
    warnings: [],
    expense_breakdown: {
      flights_inr: 0, visa_inr: null, accommodation_inr: 0, activities_inr: 0,
      food_inr: 0, local_transport_inr: 0, shopping_inr: 0, emergency_buffer_inr: 0,
      total_inr: 0, destination_currency_code: '', total_destination_currency: 0, num_people: 1,
    },
    generation_tier: 'live' as const,
  },
  updated_at: '2026-08-15T00:00:00Z',
}

describe('AccountPage — continue your last trip (issue #65)', () => {
  beforeEach(() => {
    push.mockReset()
    vi.mocked(getLastItinerary).mockReset()
    signIn()
  })

  afterEach(() => {
    useAuthStore.setState(initialAuthState)
    useTripConfigStore.setState(initialTripConfigState)
    useItineraryStore.setState(initialItineraryState)
  })

  it('shows no card when the user has no saved itinerary', async () => {
    vi.mocked(getLastItinerary).mockResolvedValue(null)

    render(<AccountPage />)

    await waitFor(() => expect(getLastItinerary).toHaveBeenCalled())
    expect(screen.queryByText(/continue your last trip/i)).not.toBeInTheDocument()
  })

  it('shows a "continue your last trip" card with the destination when one exists', async () => {
    vi.mocked(getLastItinerary).mockResolvedValue(SAVED_TRIP)

    render(<AccountPage />)

    expect(await screen.findByText(/continue your last trip/i)).toBeInTheDocument()
    expect(screen.getByText(/Kyoto/)).toBeInTheDocument()
  })

  it('loads the saved trip config/itinerary and navigates to /itinerary on click', async () => {
    vi.mocked(getLastItinerary).mockResolvedValue(SAVED_TRIP)
    const user = userEvent.setup()

    render(<AccountPage />)

    const button = await screen.findByRole('button', { name: /continue trip/i })
    await user.click(button)

    await waitFor(() => expect(push).toHaveBeenCalledWith('/itinerary'))
    expect(useTripConfigStore.getState().config.destination?.city).toBe('Kyoto')
    expect(useItineraryStore.getState().days).toHaveLength(1)
    expect(useItineraryStore.getState().days[0].theme).toBe('Arrival')
  })
})
