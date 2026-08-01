import { create } from 'zustand'
import { fetchCurrentUser, login as apiLogin, logout as apiLogout, refreshSession, signup as apiSignup, type AuthUser } from '@/lib/authApi'
import { useChatStore } from '@/store/chatStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'

interface AuthStore {
  user: AuthUser | null
  status: 'idle' | 'loading' | 'authenticated' | 'unauthenticated'
  /** Where to send the user back to after they finish signing in — set by
   * the itinerary-generation gate right before redirecting to /signup. */
  returnTo: string | null

  hydrate: () => Promise<void>
  login: (email: string, password: string) => Promise<AuthUser>
  signup: (input: { email: string; password: string; display_name?: string; consent_accepted: boolean }) => Promise<AuthUser>
  logout: () => Promise<void>
  setReturnTo: (path: string | null) => void
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  status: 'idle',
  returnTo: null,

  hydrate: async () => {
    set({ status: 'loading' })
    // The 15-minute access token may have expired since the user's last
    // visit even though they're still genuinely signed in (refresh token
    // lasts 30 days) — try a silent refresh before concluding logged-out.
    let user = await fetchCurrentUser()
    if (!user) {
      user = await refreshSession()
    }
    set({ user, status: user ? 'authenticated' : 'unauthenticated' })
  },

  login: async (email, password) => {
    const user = await apiLogin({ email, password })
    set({ user, status: 'authenticated' })
    return user
  },

  signup: async (input) => {
    const user = await apiSignup(input)
    set({ user, status: 'authenticated' })
    return user
  },

  logout: async () => {
    // Best-effort: a failed or rate-limited call to the API must not leave the
    // browser believing it is still signed in. The server-side revocation is
    // the authoritative half, but the local session has to end either way —
    // otherwise a network blip makes "Log out" silently do nothing.
    try {
      await apiLogout()
    } catch {
      // deliberately swallowed — see above
    }
    // Clear the trip out of memory *and* sessionStorage. Without this a
    // generated itinerary stayed on screen after logging out, and remained
    // restorable by anyone using the same tab afterwards.
    useItineraryStore.getState().reset()
    useTripConfigStore.getState().resetConfig()
    useChatStore.getState().clearHistory()
    useItineraryStore.persist.clearStorage()
    useTripConfigStore.persist.clearStorage()
    set({ user: null, status: 'unauthenticated' })
  },

  setReturnTo: (path) => set({ returnTo: path }),
}))
