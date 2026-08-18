'use client'

import { useEffect } from 'react'
import { useAuthStore } from '@/store/authStore'
import { useAppStore } from '@/store/appStore'
import { getPendingGeneration } from '@/lib/pendingGeneration'
import { logClientEvent } from '@/lib/analyticsBeacon'

/** Hydrates the auth session on first load (calls GET /auth/me once) and
 * fires a best-effort session_start analytics beacon. Renders nothing. */
export function AuthHydrator() {
  const hydrate = useAuthStore((state) => state.hydrate)
  const authStatus = useAuthStore((state) => state.status)

  useEffect(() => {
    hydrate()
    logClientEvent('session_start')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Bug fix: re-open the wizard once sign-in completes if a trip config is
  // waiting to resume generation (see lib/pendingGeneration.ts). Google SSO
  // does a full-page round trip through accounts.google.com and back, which
  // wipes `wizardOpen` — plain in-memory Zustand state — along with
  // everything else in the JS heap. Without this, the user lands back on a
  // fresh "/" with the wizard closed, so <LLMWizard /> (only rendered while
  // wizardOpen is true) never mounts and its own resume-after-auth effect
  // never gets a chance to run — the saved config just sits unused in
  // sessionStorage, and to the user it looks like everything they typed
  // before signing in was lost. AuthHydrator is the one thing guaranteed to
  // be mounted on every route (root layout), so it's the right place to
  // kick the wizard back open the moment auth resolves to authenticated.
  useEffect(() => {
    if (authStatus === 'authenticated' && getPendingGeneration()) {
      useAppStore.getState().openWizard()
    }
  }, [authStatus])

  return null
}
