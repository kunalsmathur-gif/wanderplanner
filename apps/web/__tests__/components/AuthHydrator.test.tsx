import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { AuthHydrator } from '@/components/common/AuthHydrator'
import { useAuthStore } from '@/store/authStore'
import { useAppStore } from '@/store/appStore'
import { savePendingGeneration, clearPendingGeneration } from '@/lib/pendingGeneration'
import type { TripConfig } from '@/types'

vi.mock('@/lib/analyticsBeacon', () => ({
  logClientEvent: vi.fn(),
}))

const initialAuthState = useAuthStore.getState()
const initialAppState = useAppStore.getState()

const SAVED_CONFIG = {
  destination: { city: 'Kyoto', country: 'Japan', lat: 35.0, lon: 135.8 },
} as unknown as TripConfig

describe('AuthHydrator — reopens the wizard to resume a pending generation after Google SSO', () => {
  beforeEach(() => {
    // hydrate() is only ever called once per mount here — stub it to a
    // no-op so tests control `status` directly via setState instead of
    // racing a real fetchCurrentUser()/refreshSession() network call.
    useAuthStore.setState({ ...initialAuthState, hydrate: vi.fn(async () => {}), status: 'idle' })
    useAppStore.setState({ ...initialAppState, wizardOpen: false })
    clearPendingGeneration()
  })

  afterEach(() => {
    useAuthStore.setState(initialAuthState)
    useAppStore.setState(initialAppState)
    clearPendingGeneration()
  })

  it('opens the wizard once auth resolves to authenticated when a pending generation exists', async () => {
    savePendingGeneration(SAVED_CONFIG)

    render(<AuthHydrator />)
    expect(useAppStore.getState().wizardOpen).toBe(false)

    // Simulate the Google SSO round trip completing and auth hydrating.
    act(() => {
      useAuthStore.setState({ status: 'authenticated' })
    })

    await waitFor(() => expect(useAppStore.getState().wizardOpen).toBe(true))
  })

  it('does not open the wizard on a normal authenticated load with nothing pending', async () => {
    render(<AuthHydrator />)

    act(() => {
      useAuthStore.setState({ status: 'authenticated' })
    })

    // Give any (incorrect) async effect a tick to fire before asserting.
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(useAppStore.getState().wizardOpen).toBe(false)
  })

  it('does not open the wizard for a signed-out visitor even if something is pending', async () => {
    savePendingGeneration(SAVED_CONFIG)

    render(<AuthHydrator />)
    act(() => {
      useAuthStore.setState({ status: 'unauthenticated' })
    })

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(useAppStore.getState().wizardOpen).toBe(false)
  })
})
