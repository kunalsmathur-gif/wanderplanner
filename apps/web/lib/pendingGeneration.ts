import type { TripConfig } from '@/types'

// A trip config that was fully filled in by the wizard but couldn't be
// generated yet because the user wasn't signed in. Persisted to
// sessionStorage (not just a Zustand store) because Google SSO does a full
// browser navigation away from and back to the app, which would otherwise
// wipe all in-memory state.
const STORAGE_KEY = 'wp_pending_trip_config'

export function savePendingGeneration(config: TripConfig) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(config))
  } catch {
    // sessionStorage unavailable (private browsing, SSR, etc.) — safe to ignore,
    // user will just need to click "Generate" again after signing in.
  }
}

export function getPendingGeneration(): TripConfig | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as TripConfig) : null
  } catch {
    return null
  }
}

export function clearPendingGeneration() {
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}
