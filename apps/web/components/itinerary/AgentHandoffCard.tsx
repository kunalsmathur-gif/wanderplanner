'use client'

import { useEffect, useMemo, useState } from 'react'
import { usePathname } from 'next/navigation'
import { createAgentLead } from '@/lib/api'
import { formatCurrency } from '@/lib/format'
import { useAuthStore } from '@/store/authStore'
import { useTripConfigStore } from '@/store/tripConfigStore'

const CONCIERGE_WHATSAPP_NUMBER = process.env.NEXT_PUBLIC_AGENT_CONCIERGE_WHATSAPP ?? ''

type SubmitState = 'idle' | 'loading' | 'success' | 'error'

function getBudgetTier(amount: number): string {
  if (amount <= 0) return 'Flexible'
  if (amount < 75_000) return 'Value'
  if (amount < 200_000) return 'Mid-range'
  return 'Premium'
}

export function AgentHandoffCard() {
  const pathname = usePathname()
  const userEmail = useAuthStore((s) => s.user?.email ?? '')
  const config = useTripConfigStore((s) => s.config)

  const [email, setEmail] = useState(userEmail)
  const [state, setState] = useState<SubmitState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [whatsAppUrl, setWhatsAppUrl] = useState<string | null>(null)

  useEffect(() => {
    if (userEmail) setEmail(userEmail)
  }, [userEmail])

  const tripSummary = useMemo(() => {
    const destination = config.destination?.city || config.destination_country || ''
    const travelers = config.group.adults + config.group.seniors + config.group.infants + config.group.kids.length
    const budgetTier = getBudgetTier(config.budget.amount)
    const shareUrl =
      typeof window !== 'undefined' && pathname?.startsWith('/t/')
        ? window.location.href
        : null

    return {
      destination,
      dates: config.dates,
      pax: travelers,
      budget_tier: budgetTier,
      budget_display: config.budget.amount > 0 ? formatCurrency(config.budget.amount, config.budget.currency) : null,
      share_url: shareUrl,
    }
  }, [config, pathname])

  if (!tripSummary.destination) return null

  const buildWhatsAppUrl = () => {
    if (!CONCIERGE_WHATSAPP_NUMBER) return null

    const message = [
      'Hi! I’d like help booking this Wanderplanner itinerary.',
      `Destination: ${tripSummary.destination}`,
      tripSummary.dates.start || tripSummary.dates.end
        ? `Dates: ${tripSummary.dates.start ?? 'Flexible'} → ${tripSummary.dates.end ?? 'Flexible'}`
        : 'Dates: Flexible',
      `Pax: ${tripSummary.pax || 1}`,
      `Budget tier: ${tripSummary.budget_tier}${tripSummary.budget_display ? ` (${tripSummary.budget_display})` : ''}`,
      tripSummary.share_url ? `Share link: ${tripSummary.share_url}` : null,
    ].filter(Boolean).join('\n')

    return `https://wa.me/${CONCIERGE_WHATSAPP_NUMBER}?text=${encodeURIComponent(message)}`
  }

  async function handleSubmit() {
    setState('loading')
    setError(null)

    try {
      await createAgentLead({
        email,
        destination: tripSummary.destination,
        trip_config_summary: tripSummary,
      })

      const nextUrl = buildWhatsAppUrl()
      setWhatsAppUrl(nextUrl)
      setState('success')
      if (nextUrl) {
        window.open(nextUrl, '_blank', 'noopener,noreferrer')
      }
    } catch {
      setState('error')
      setError('Couldn’t send your request just now. Please retry.')
    }
  }

  return (
    <section className="rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--_muted-fg)]">
            🧭 Local Expert Help
          </p>
          <h3 className="mt-1 text-lg font-bold text-[var(--_fg)] [font-family:var(--font-display)]">
            Get This Itinerary Booked by a Local Expert
          </h3>
          <p className="mt-2 text-sm leading-relaxed text-[var(--_muted-fg)]">
            A destination specialist reviews your plan and gets back to you personally — no bots, no generic replies.
          </p>
        </div>
        <span className="rounded-full border border-[var(--_accent)]/20 bg-[var(--_accent)]/10 px-3 py-1 text-xs font-semibold text-[var(--_accent)]">
          Replies within 24 hours, guaranteed
        </span>
      </div>

      {state === 'success' ? (
        <div className="mt-4 rounded-xl border border-[var(--_success)]/25 bg-[var(--_success)]/10 p-4">
          <p className="text-sm font-medium text-[var(--_fg)]">
            ✅ Request sent — expect a reply within 24 hours
          </p>
          <button
            type="button"
            onClick={() => whatsAppUrl && window.open(whatsAppUrl, '_blank', 'noopener,noreferrer')}
            disabled={!whatsAppUrl}
            className="btn btn-outline mt-3 w-full rounded-xl text-sm disabled:opacity-50"
            title={whatsAppUrl ? 'Continue on WhatsApp' : 'Set NEXT_PUBLIC_AGENT_CONCIERGE_WHATSAPP to enable this'}
          >
            💬 Continue on WhatsApp
          </button>
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[var(--_muted-fg)]">
              Email for the specialist reply
            </span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="input"
              disabled={state === 'loading'}
            />
          </label>

          {error && (
            <div className="rounded-xl border border-[var(--_destructive)]/20 bg-[var(--_destructive)]/10 px-3 py-2 text-sm text-[var(--_destructive)]">
              {error}
            </div>
          )}

          <button
            type="button"
            onClick={handleSubmit}
            disabled={state === 'loading' || !email.trim()}
            className="btn btn-accent w-full rounded-xl"
          >
            {state === 'loading' ? 'Sending…' : 'Get Quotation'}
          </button>

          {state === 'error' && (
            <button
              type="button"
              onClick={handleSubmit}
              className="text-sm font-medium text-[var(--_primary)] hover:underline"
            >
              Retry
            </button>
          )}
        </div>
      )}
    </section>
  )
}
