'use client'

import { useEffect, useState } from 'react'
import { fetchAuthConfig } from '@/lib/authApi'
import { GoogleSignInButton } from '@/components/common/GoogleSignInButton'

/**
 * Wraps the "Continue with Google" button + its "or" divider, and hides both
 * entirely unless the backend confirms Google OAuth is actually configured
 * (GOOGLE_CLIENT_ID/SECRET set) — otherwise clicking it always 503s
 * ("Google sign-in is not configured"). Defaults to hidden while the check
 * is in flight and on any failure, so the UI fails closed rather than
 * flashing a button that's known to be broken.
 */
export function GoogleSsoSection({ returnTo = '/' }: { returnTo?: string }) {
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchAuthConfig().then((config) => {
      if (!cancelled) setEnabled(config.google_sso_enabled)
    })
    return () => {
      cancelled = true
    }
  }, [])

  if (!enabled) return null

  return (
    <>
      <GoogleSignInButton returnTo={returnTo} />
      <div className="my-5 flex items-center gap-3">
        <div className="h-px flex-1 bg-[var(--_border)]" />
        <span className="text-xs font-medium uppercase tracking-wide text-[var(--_muted-fg)]">or</span>
        <div className="h-px flex-1 bg-[var(--_border)]" />
      </div>
    </>
  )
}
