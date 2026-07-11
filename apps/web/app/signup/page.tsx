'use client'

import { Suspense, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import { AuthLayout } from '@/components/common/AuthLayout'
import { GoogleSsoSection } from '@/components/common/GoogleSsoSection'
import { useAuthStore } from '@/store/authStore'
import { authErrorMessage } from '@/lib/authApi'

export default function SignupPage() {
  return (
    <Suspense fallback={null}>
      <SignupForm />
    </Suspense>
  )
}

function SignupForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const returnTo = searchParams.get('returnTo') || '/'
  const signup = useAuthStore((state) => state.signup)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [consentAccepted, setConsentAccepted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (!consentAccepted) {
      setError('Please accept the Terms of Service and Privacy Policy to continue.')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }

    setSubmitting(true)
    try {
      await signup({ email, password, display_name: displayName || undefined, consent_accepted: consentAccepted })
      router.push(returnTo)
    } catch (err) {
      setError(authErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout
      title="Create your free account"
      subtitle="Free sign-up in seconds — no credit card required."
      footer={
        <>
          Already have an account?{' '}
          <Link href={`/login?returnTo=${encodeURIComponent(returnTo)}`} className="font-semibold text-[var(--_primary)] hover:underline">
            Log in
          </Link>
        </>
      }
    >
      <GoogleSsoSection returnTo={returnTo} />

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="display_name" className="mb-1.5 block text-sm font-medium text-[var(--_fg)]">
            Name
          </label>
          <input
            id="display_name"
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Your name"
            className="input w-full rounded-xl border border-[var(--_border)] bg-[var(--_card)] py-2.5 px-3.5 text-sm text-[var(--_fg)] placeholder:text-[var(--_muted-fg)] focus:border-[var(--_primary)] focus:outline-none"
          />
        </div>

        <div>
          <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-[var(--_fg)]">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="input w-full rounded-xl border border-[var(--_border)] bg-[var(--_card)] py-2.5 px-3.5 text-sm text-[var(--_fg)] placeholder:text-[var(--_muted-fg)] focus:border-[var(--_primary)] focus:outline-none"
          />
        </div>

        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-[var(--_fg)]">
            Password
          </label>
          <div className="relative">
            <input
              id="password"
              type={showPassword ? 'text' : 'password'}
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              className="input w-full rounded-xl border border-[var(--_border)] bg-[var(--_card)] py-2.5 px-3.5 pr-10 text-sm text-[var(--_fg)] placeholder:text-[var(--_muted-fg)] focus:border-[var(--_primary)] focus:outline-none"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--_muted-fg)] hover:text-[var(--_fg)]"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>

        {/* Minimized consent copy with hyperlinks to full legal text — matches
            the common Indian travel-platform pattern (single checkbox, detail
            lives behind the links) rather than a wall of text on the form. */}
        <label className="flex items-start gap-2.5 text-sm text-[var(--_muted-fg)]">
          <input
            type="checkbox"
            checked={consentAccepted}
            onChange={(e) => setConsentAccepted(e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 rounded border-[var(--_border)] accent-[var(--_primary)]"
          />
          <span>
            I agree to the{' '}
            <Link href="/terms" target="_blank" className="font-medium text-[var(--_primary)] hover:underline">
              Terms of Service
            </Link>{' '}
            and{' '}
            <Link href="/privacy" target="_blank" className="font-medium text-[var(--_primary)] hover:underline">
              Privacy Policy
            </Link>
            .
          </span>
        </label>

        {error && <p className="text-sm text-[var(--_destructive)]">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="btn btn-accent w-full justify-center gap-2 rounded-xl py-2.5 text-sm font-bold disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting && <Loader2 size={16} className="animate-spin" />}
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
      </form>
    </AuthLayout>
  )
}
