'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { deleteMyAccount, authErrorMessage } from '@/lib/authApi'
import { WanderplannerLogo } from '@/components/common/WanderplannerLogo'

export default function AccountPage() {
  const router = useRouter()
  const user = useAuthStore((s) => s.user)
  const status = useAuthStore((s) => s.status)
  const logout = useAuthStore((s) => s.logout)

  const [confirmText, setConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showConfirm, setShowConfirm] = useState(false)

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

          <div className="mt-8 border-t border-[var(--_border)] pt-6">
            <h2 className="flex items-center gap-2 text-base font-semibold text-[var(--_destructive)]">
              <AlertTriangle size={18} />
              Danger zone
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
                <input
                  type="text"
                  value={confirmText}
                  onChange={(e) => setConfirmText(e.target.value)}
                  placeholder="DELETE"
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
