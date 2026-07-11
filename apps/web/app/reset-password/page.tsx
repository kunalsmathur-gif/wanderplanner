'use client'

import { Suspense, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { CheckCircle2, Eye, EyeOff, Loader2 } from 'lucide-react'
import { AuthLayout } from '@/components/common/AuthLayout'
import { resetPassword, authErrorMessage } from '@/lib/authApi'

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  )
}

function ResetPasswordForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const token = searchParams.get('token') || ''

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (!token) {
      setError('This reset link is missing its token. Please request a new one.')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setSubmitting(true)
    try {
      await resetPassword(token, password)
      setDone(true)
    } catch (err) {
      setError(authErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <AuthLayout title="Password updated" subtitle="">
        <div className="flex flex-col items-center gap-3 py-4 text-center">
          <CheckCircle2 size={40} className="text-[var(--_success)]" />
          <p className="text-sm text-[var(--_muted-fg)]">
            Your password has been changed. All existing sessions have been signed out for security.
          </p>
          <button
            type="button"
            onClick={() => router.push('/login')}
            className="btn btn-accent mt-2 rounded-xl px-6 py-2.5 text-sm font-bold"
          >
            Log in
          </button>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Choose a new password"
      subtitle="Enter a new password for your account."
      footer={
        <Link href="/login" className="font-semibold text-[var(--_primary)] hover:underline">
          Back to log in
        </Link>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-[var(--_fg)]">
            New password
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

        <div>
          <label htmlFor="confirm_password" className="mb-1.5 block text-sm font-medium text-[var(--_fg)]">
            Confirm new password
          </label>
          <input
            id="confirm_password"
            type={showPassword ? 'text' : 'password'}
            required
            minLength={8}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Re-enter your new password"
            className="input w-full rounded-xl border border-[var(--_border)] bg-[var(--_card)] py-2.5 px-3.5 text-sm text-[var(--_fg)] placeholder:text-[var(--_muted-fg)] focus:border-[var(--_primary)] focus:outline-none"
          />
        </div>

        {error && <p className="text-sm text-[var(--_destructive)]">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="btn btn-accent w-full justify-center gap-2 rounded-xl py-2.5 text-sm font-bold disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting && <Loader2 size={16} className="animate-spin" />}
          {submitting ? 'Updating…' : 'Update password'}
        </button>
      </form>
    </AuthLayout>
  )
}
