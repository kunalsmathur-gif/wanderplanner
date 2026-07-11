'use client'

import { useEffect } from 'react'
import { useAuthStore } from '@/store/authStore'
import { logClientEvent } from '@/lib/analyticsBeacon'

/** Hydrates the auth session on first load (calls GET /auth/me once) and
 * fires a best-effort session_start analytics beacon. Renders nothing. */
export function AuthHydrator() {
  const hydrate = useAuthStore((state) => state.hydrate)

  useEffect(() => {
    hydrate()
    logClientEvent('session_start')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return null
}
