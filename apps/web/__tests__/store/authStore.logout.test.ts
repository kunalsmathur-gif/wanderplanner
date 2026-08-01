import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/store/authStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useChatStore } from '@/store/chatStore'

const logoutMock = vi.fn()

vi.mock('@/lib/authApi', () => ({
  logout: () => logoutMock(),
  login: vi.fn(),
  signup: vi.fn(),
  fetchCurrentUser: vi.fn(),
  refreshSession: vi.fn(),
}))

function seedSignedInTrip() {
  useAuthStore.setState({
    user: { id: 'u1', email: 'a@b.c', display_name: null, is_admin: false, auth_provider: 'password' },
    status: 'authenticated',
  })
  useItineraryStore.getState().setDays(
    [{ day: 1, date: '2026-01-01', title: 'Day 1', items: [] }] as never,
    80,
  )
  useTripConfigStore.getState().setDestination({ city: 'Tokyo', country: 'JP', lat: 35.6, lon: 139.6 })
  useChatStore.getState().addMessage({ role: 'user', content: 'make day 1 lighter' } as never)
}

describe('authStore.logout', () => {
  beforeEach(() => {
    logoutMock.mockReset().mockResolvedValue(undefined)
    sessionStorage.clear()
  })

  it('clears the trip out of memory, not just the user', async () => {
    // The reported bug: logging out on the itinerary page left the itinerary
    // on screen, because only `user` was reset.
    seedSignedInTrip()
    expect(useItineraryStore.getState().days).toHaveLength(1)

    await useAuthStore.getState().logout()

    expect(useAuthStore.getState().user).toBeNull()
    expect(useAuthStore.getState().status).toBe('unauthenticated')
    expect(useItineraryStore.getState().days).toHaveLength(0)
    expect(useTripConfigStore.getState().config.destination).toBeNull()
    expect(useChatStore.getState().messages).toHaveLength(0)
  })

  it('clears the persisted copy too, so the trip is not restorable afterwards', async () => {
    seedSignedInTrip()
    await useItineraryStore.persist.rehydrate()
    expect(sessionStorage.getItem('wanderplanner-itinerary')).not.toBeNull()

    await useAuthStore.getState().logout()

    // Anyone using this tab next must not be able to refresh the trip back.
    const restored = sessionStorage.getItem('wanderplanner-itinerary')
    expect(restored === null || !restored.includes('"days":[{')).toBe(true)
  })

  it('still ends the local session when the API call fails', async () => {
    // A rate-limited or offline logout must not leave the browser believing
    // it is signed in — "Log out" silently doing nothing was half of the bug.
    logoutMock.mockRejectedValue(new Error('network'))
    seedSignedInTrip()

    await expect(useAuthStore.getState().logout()).resolves.toBeUndefined()

    expect(useAuthStore.getState().user).toBeNull()
    expect(useItineraryStore.getState().days).toHaveLength(0)
  })
})
