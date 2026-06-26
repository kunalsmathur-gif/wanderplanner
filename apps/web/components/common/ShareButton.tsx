'use client'

import { useState } from 'react'
import { Share2, Check, Loader2, Copy } from 'lucide-react'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useWizardChatStore } from '@/store/wizardChatStore'
import { shareTrip } from '@/lib/api'

export function ShareButton() {
  const [status, setStatus] = useState<'idle' | 'loading' | 'copied' | 'error'>('idle')
  const [shareUrl, setShareUrl] = useState<string | null>(null)

  async function handleShare() {
    if (shareUrl) {
      navigator.clipboard.writeText(window.location.origin + shareUrl)
      setStatus('copied')
      setTimeout(() => setStatus('idle'), 2000)
      return
    }

    setStatus('loading')
    try {
      const { days, alignmentScore, expenseBreakdown } = useItineraryStore.getState()
      const { config } = useTripConfigStore.getState()
      const { collectedLabels } = useWizardChatStore.getState()

      const destLabel = config.destination
        ? [config.destination.city, config.destination.country].filter(Boolean).join(', ')
        : config.destination_country ?? ''

      const result = await shareTrip({
        itinerary: { days, alignment_score: alignmentScore, expense_breakdown: expenseBreakdown },
        trip_config: config as unknown as object,
        labels: collectedLabels,
        destination_label: destLabel,
      })

      setShareUrl(result.url)
      navigator.clipboard.writeText(window.location.origin + result.url)
      setStatus('copied')
      setTimeout(() => setStatus('idle'), 3000)
    } catch {
      setStatus('error')
      setTimeout(() => setStatus('idle'), 2000)
    }
  }

  const label =
    status === 'loading' ? 'Generating…'
    : status === 'copied' ? 'Link copied!'
    : status === 'error'  ? 'Failed — retry'
    : shareUrl             ? 'Copy link'
    : 'Share'

  const Icon =
    status === 'loading' ? Loader2
    : status === 'copied' ? Check
    : shareUrl             ? Copy
    : Share2

  return (
    <button
      type="button"
      onClick={handleShare}
      disabled={status === 'loading'}
      title={shareUrl ? `${window?.location?.origin}${shareUrl}` : 'Generate a shareable link'}
      className={[
        'flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition-all',
        status === 'copied'
          ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400'
          : status === 'error'
          ? 'bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400'
          : 'bg-[var(--_card-elevated)] text-[var(--_fg)] hover:border-[var(--_primary)] hover:text-[var(--_primary)]',
        'border border-[var(--_border)]',
      ].join(' ')}
    >
      <Icon size={13} className={status === 'loading' ? 'animate-spin' : ''} />
      {label}
    </button>
  )
}
