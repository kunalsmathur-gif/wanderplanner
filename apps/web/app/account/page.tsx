'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { AlertTriangle, Loader2, MapPin } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { deleteMyAccount, authErrorMessage } from '@/lib/authApi'
import { getLastItinerary, type LastItineraryResult } from '@/lib/api'
import { loadLastItinerary } from '@/lib/resumeLastItinerary'
import { WanderplannerLogo } from '@/components/common/WanderplannerLogo'

export default function AccountPage() {
  const deleteConfirmationInputId = 'delete-account-confirmation'
  const router = useRouter()
  const user = useAuthStore((s) => s.user)
  const status = useAuthStore((s) => s.status)
  const logout = useAuthStore((s) => s.logout)

  const [confirmText, setConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showConfirm, setShowConfirm] = useState(false)

  // "Continue your last trip" (issue #65) — only ever shown to a signed-in
  // user with a saved itinerary, never a guest. `undefined` = still
  // checking, `null` = confirmed none (or the check failed) — kept
  // distinct so the card doesn't flash empty before the request resolves.
  const [lastItinerary, setLastItinerary] = useState<LastItineraryResult | null | undefined>(undefined)
  const [resuming, setResuming] = useState(false)

  useEffect(() => {
    if (status !== 'authenticated') return
    let cancelled = false
    getLastItinerary().then((result) => {
      if (!cancelled) setLastItinerary(result)
    })
    return () => {
      cancelled = true
    }
  }, [status])

  if (status === 'loading' || status === 'idle') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--_bg)]">
        <Loader2 className="animate-spin text-[var(--_muted-fg)]" size={24} />
      </div>
    )
  }

  if (status === 'unauthenticated' || !user) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[var(--_bg)] px-4 text-center">
        <p className="text-[var(--_fg)]">You need to be signed in to view account settings.</p>
        <Link href="/login?returnTo=/account" className="btn btn-accent rounded-xl px-5 py-2.5 text-sm font-semibold">
          Log in
        </Link>
      </div>
    )
  }

  async function handleResumeLastTrip() {
    setResuming(true)
    const resumed = await loadLastItinerary()
    if (resumed) {
      router.push('/itinerary')
    } else {
      // The saved trip vanished between the check above and the click
      // (expired, or cleared) — quietly drop the card rather than navigate
      // to an itinerary page with nothing to show.
      setLastItinerary(null)
      setResuming(false)
    }
  }

  function formatDateRange(dates: LastItineraryResult['trip_config']['dates']): string {
    if (!dates?.start || !dates?.end) return ''
    const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }
    try {
      return `${new Date(dates.start).toLocaleDateString('en-IN', opts)} – ${new Date(dates.end).toLocaleDateString('en-IN', opts)}`
    } catch {
      return ''
    }
  }

  async function handleDelete() {
    setError(null)
    setDeleting(true)
    try {
      await deleteMyAccount()
      // Local session state is now stale server-side — clear it and bounce home.
      await logout().catch(() => {})
      router.push('/')
    } catch (err) {
      setError(authErrorMessage(err))
      setDeleting(false)
    }
  }

  return (
    <div className="min-h-screen bg-[var(--_bg)] px-4 py-12">
      <div className="mx-auto max-w-2xl">
        <Link href="/" className="mb-8 inline-block">
          <WanderplannerLogo size="sm" />
        </Link>

        <div className="rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-8 shadow-sm">
          <h1 className="text-2xl font-bold text-[var(--_fg)] [font-family:var(--font-display)]">Account settings</h1>

          <div className="mt-6 space-y-1 text-sm">
            <p className="text-[var(--_muted-fg)]">Signed in as</p>
            <p className="font-medium text-[var(--_fg)]">{user.display_name || user.email}</p>
            {user.email && <p className="text-[var(--_muted-fg)]">{user.email}</p>}
          </div>

          {lastItinerary && (
            <div className="mt-8 rounded-xl border border-[var(--_border)] bg-[var(--_bg)] p-5">
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--_primary)]/10">
                  <MapPin size={16} className="text-[var(--_primary)]" />
                </div>
                <div className="min-w-0 flex-1">
                  <h2 className="text-base font-semibold text-[var(--_fg)]">Continue your last trip</h2>
                  <p className="mt-1 text-sm text-[var(--_muted-fg)]">
                    {lastItinerary.trip_config.destination?.city || lastItinerary.trip_config.destination_country}
                    {formatDateRange(lastItinerary.trip_config.dates) && ` · ${formatDateRange(lastItinerary.trip_config.dates)}`}
                  </p>
                  <button
                    type="button"
                    onClick={handleResumeLastTrip}
                    disabled={resuming}
                    className="btn btn-accent mt-3 rounded-xl px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {resuming && <Loader2 size={14} className="mr-1.5 inline animate-spin" />}
                    {resuming ? 'Loading…' : 'Continue trip'}
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="mt-8 border-t border-[var(--_border)] pt-6">
            <h2 className="flex items-center gap-2 text-base font-semibold text-[var(--_fg)]">
              <AlertTriangle size={18} className="text-[var(--_destructive)]" />
              Manage account
            </h2>
            <p className="mt-2 text-sm text-[var(--_muted-fg)]">
              Permanently delete your account and all personal data (email, password, saved trips). This cannot be
              undone. Some anonymized, aggregated usage data may be retained — see our{' '}
              <Link href="/privacy" className="font-medium text-[var(--_primary)] hover:underline">
                Privacy Policy
              </Link>
              .
            </p>

            {!showConfirm ? (
              <button
                type="button"
                onClick={() => setShowConfirm(true)}
                className="btn btn-outline mt-4 rounded-xl border-[var(--_destructive)] px-4 py-2 text-sm font-semibold text-[var(--_destructive)] hover:bg-[var(--_destructive)] hover:text-white"
              >
                Delete my account
              </button>
            ) : (
              <div className="mt-4 space-y-3 rounded-xl border border-[var(--_destructive)] bg-[var(--_destructive)]/5 p-4">
                <p className="text-sm font-medium text-[var(--_fg)]">
                  Type <span className="font-mono">DELETE</span> to confirm.
                </p>
                <label htmlFor={deleteConfirmationInputId} className="block text-sm font-medium text-[var(--_fg)]">
                  Confirmation phrase
                </label>
                <input
                  id={deleteConfirmationInputId}
                  type="text"
                  value={confirmText}
                  onChange={(e) => setConfirmText(e.target.value)}
                  placeholder="DELETE"
                  maxLength={20}
                  className="input w-full rounded-xl border border-[var(--_border)] bg-[var(--_card)] py-2.5 px-3.5 text-sm text-[var(--_fg)] focus:border-[var(--_primary)] focus:outline-none"
                />
                {error && <p className="text-sm text-[var(--_destructive)]">{error}</p>}
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={confirmText !== 'DELETE' || deleting}
                    onClick={handleDelete}
                    className="btn rounded-xl bg-[var(--_destructive)] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {deleting && <Loader2 size={14} className="mr-1.5 inline animate-spin" />}
                    {deleting ? 'Deleting…' : 'Permanently delete'}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setShowConfirm(false); setConfirmText('') }}
                    className="btn btn-outline rounded-xl px-4 py-2 text-sm font-semibold"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
