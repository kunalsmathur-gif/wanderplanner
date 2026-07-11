'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Loader2, MailCheck } from 'lucide-react'
import { AuthLayout } from '@/components/common/AuthLayout'
import { forgotPassword, authErrorMessage } from '@/lib/authApi'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await forgotPassword(email)
      // Backend always returns a generic success regardless of whether the
      // email exists, to prevent account enumeration — mirror that here.
      setSent(true)
    } catch (err) {
      setError(authErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  if (sent) {
    return (
      <AuthLayout title="Check your email" subtitle="">
        <div className="flex flex-col items-center gap-3 py-4 text-center">
          <MailCheck size={40} className="text-[var(--_primary)]" />
          <p className="text-sm text-[var(--_muted-fg)]">
            If an account exists for <strong className="text-[var(--_fg)]">{email}</strong>, we've sent a link to
            reset your password. It expires in 30 minutes.
          </p>
          <Link href="/login" className="mt-2 text-sm font-semibold text-[var(--_primary)] hover:underline">
            Back to log in
          </Link>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Forgot your password?"
      subtitle="Enter your email and we'll send you a reset link."
      footer={
        <Link href="/login" className="font-semibold text-[var(--_primary)] hover:underline">
          Back to log in
        </Link>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
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

        {error && <p className="text-sm text-[var(--_destructive)]">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="btn btn-accent w-full justify-center gap-2 rounded-xl py-2.5 text-sm font-bold disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting && <Loader2 size={16} className="animate-spin" />}
          {submitting ? 'Sending…' : 'Send reset link'}
        </button>
      </form>
    </AuthLayout>
  )
}
