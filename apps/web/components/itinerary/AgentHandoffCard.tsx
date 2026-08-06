'use client'

import { useEffect, useMemo, useState } from 'react'
import { usePathname } from 'next/navigation'
import { createAgentLead } from '@/lib/api'
import { formatCurrency } from '@/lib/format'
import { useAuthStore } from '@/store/authStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useFeedbackPromptStore } from '@/store/feedbackPromptStore'
import { AgentQuoteModal } from '@/components/itinerary/AgentQuoteModal'

const CONCIERGE_WHATSAPP_NUMBER = process.env.NEXT_PUBLIC_AGENT_CONCIERGE_WHATSAPP ?? ''
const MAX_NOTES_WORDS = 100

type SubmitState = 'idle' | 'loading' | 'success' | 'error'

function countWords(text: string): number {
  const trimmed = text.trim()
  return trimmed ? trimmed.split(/\s+/).length : 0
}

/** Truncates to at most `MAX_NOTES_WORDS` words rather than blocking further
 * typing outright — friendlier than a hard-disabled textarea once the limit
 * is hit. */
function clampToWordLimit(text: string): string {
  const words = text.split(/\s+/)
  if (words.length <= MAX_NOTES_WORDS) return text
  return words.slice(0, MAX_NOTES_WORDS).join(' ')
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

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
  const days = useItineraryStore((s) => s.days)
  const expenseBreakdown = useItineraryStore((s) => s.expenseBreakdown)

  const [email, setEmail] = useState(userEmail)
  const [notes, setNotes] = useState('')
  const [state, setState] = useState<SubmitState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [whatsAppUrl, setWhatsAppUrl] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [alreadySentToday, setAlreadySentToday] = useState(false)

  const notesWordCount = countWords(notes)

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

  // A simple HTML rendering of the AI-generated itinerary, embedded directly
  // in the agent-facing email body (in addition to the PDF attachment) so
  // the agent doesn't have to open an attachment just to see the plan.
  function buildItineraryHtml(): string | null {
    if (!days.length) return null

    const dayBlocks = days.map((day) => {
      const items = day.items
        .map((item) => `<li>${escapeHtml(item.time_start)}–${escapeHtml(item.time_end)} · <strong>${escapeHtml(item.title)}</strong>${item.description ? `: ${escapeHtml(item.description)}` : ''}</li>`)
        .join('')
      return `<h4>Day ${day.day_number}: ${escapeHtml(day.theme)}${day.date ? ` · ${escapeHtml(day.date)}` : ''}</h4><ul>${items}</ul>`
    }).join('')

    const total = expenseBreakdown?.total_inr
      ? `<p><strong>Estimated total cost:</strong> ₹${expenseBreakdown.total_inr.toLocaleString('en-IN')} for ${expenseBreakdown.num_people} traveler(s)</p>`
      : ''

    return `${dayBlocks}${total}`
  }

  // Renders the same PDF as the "Download Itinerary PDF" button, but keeps
  // it as a base64 string in memory to attach to the quotation-request
  // email instead of triggering a browser download.
  async function buildItineraryPdfBase64(): Promise<string | null> {
    if (!days.length) return null
    try {
      const [{ pdf }, { ItineraryDocument }] = await Promise.all([
        import('@react-pdf/renderer'),
        import('@/components/pdf/ItineraryDocument'),
      ])
      const blob = await pdf(
        <ItineraryDocument days={days} config={config} expenseBreakdown={expenseBreakdown} />,
      ).toBlob()
      const buffer = await blob.arrayBuffer()
      let binary = ''
      const bytes = new Uint8Array(buffer)
      for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
      return btoa(binary)
    } catch {
      // Best-effort — a PDF-generation failure shouldn't block the lead
      // itself from going out; the agent still gets the HTML summary.
      return null
    }
  }

  async function handleSubmit() {
    setState('loading')
    setError(null)

    try {
      const [itineraryHtml, pdfBase64] = await Promise.all([
        Promise.resolve(buildItineraryHtml()),
        buildItineraryPdfBase64(),
      ])

      const result = await createAgentLead({
        email,
        destination: tripSummary.destination,
        source: 'itinerary',
        trip_config_summary: tripSummary,
        custom_notes: notes.trim() || null,
        itinerary_html: itineraryHtml,
        pdf_base64: pdfBase64,
      })

      const nextUrl = buildWhatsAppUrl()
      setWhatsAppUrl(nextUrl)
      setAlreadySentToday(result.duplicate)
      setState('success')
      // Close on success so the confirmation (and the WhatsApp follow-up) is
      // read on the card itself rather than behind a dialog the user still
      // has to dismiss.
      setModalOpen(false)
      if (nextUrl) {
        window.open(nextUrl, '_blank', 'noopener,noreferrer')
      }
      // Booking via a local expert is a strong "I'm satisfied enough to act
      // on this plan" signal — a natural moment to ask for a reaction too.
      useFeedbackPromptStore.getState().request('book')
    } catch {
      setState('error')
      setError('Couldn’t send your request just now. Please retry.')
    }
  }

  const sent = state === 'success'

  return (
    <section className="rounded-2xl border-2 border-[var(--_accent)]/40 bg-gradient-to-br from-[var(--_accent)]/8 to-[var(--_card)] p-4 shadow-md shadow-[var(--_accent)]/10">
      {/* Deliberately minimal: one line of pitch, one proof point, one action.
          Everything that needs typing lives in the modal — see
          AgentQuoteModal for why. */}
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--_muted-fg)]">
        🧭 Local Expert Help
      </p>
      <h3 className="mt-1 text-base font-bold leading-snug text-[var(--_fg)] [font-family:var(--font-display)]">
        Get this itinerary booked by a local expert
      </h3>
      <p className="mt-1.5 text-sm leading-relaxed text-[var(--_muted-fg)]">
        A destination specialist reviews your plan and replies personally.
      </p>

      {sent ? (
        <div className="mt-3 rounded-xl border border-[var(--_success)]/25 bg-[var(--_success)]/10 p-3">
          <p className="text-sm font-medium text-[var(--_fg)]">
            {alreadySentToday
              ? 'ℹ️ You already sent a request today — no need to resend, expect a reply within 24 hours'
              : '✅ Request sent — expect a reply within 24 hours'}
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
        <>
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="btn btn-accent mt-3 h-11 w-full rounded-xl text-sm shadow-md shadow-[var(--_accent)]/20"
          >
            Get Quotation
          </button>
          <p className="mt-2 text-center text-xs font-medium text-[var(--_accent)]">
            Replies within 24 hours, guaranteed
          </p>
        </>
      )}

      <AgentQuoteModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        titleId="agent-quote-modal-title"
      >
        <div className="space-y-3">
          <p className="text-sm text-[var(--_muted-fg)]">
            We&apos;ll send your {tripSummary.destination} plan to a destination specialist.
          </p>

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

          <label className="block">
            <span className="mb-1.5 flex items-center justify-between gap-2 text-xs font-medium uppercase tracking-wide text-[var(--_muted-fg)]">
              <span>Anything specific? (optional)</span>
              <span className={notesWordCount >= MAX_NOTES_WORDS ? 'text-[var(--_destructive)]' : ''}>
                {notesWordCount}/{MAX_NOTES_WORDS}
              </span>
            </span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(clampToWordLimit(e.target.value))}
              placeholder="e.g. Prefer boutique hotels, celebrating an anniversary…"
              rows={3}
              className="input resize-none"
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
            className="btn btn-accent h-11 w-full rounded-xl text-sm shadow-md shadow-[var(--_accent)]/20"
          >
            {state === 'loading' ? 'Sending…' : 'Send request'}
          </button>

          <p className="text-center text-xs text-[var(--_muted-fg)]">
            Replies within 24 hours, guaranteed
          </p>
        </div>
      </AgentQuoteModal>
    </section>
  )
}
