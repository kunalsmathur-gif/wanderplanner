'use client'

import { useState } from 'react'
import { createItineraryFeedback } from '@/lib/api'
import { useTripConfigStore } from '@/store/tripConfigStore'

type FlagState = 'idle' | 'expanded' | 'loading' | 'sent' | 'error'

// Low-friction, itinerary-wide "this missed the mark" flag — one button,
// an optional one-line reason, no modal. Tied to the exact TripConfig that
// produced the itinerary (a full snapshot, not just an itinerary ID, since
// no itinerary ID is persisted today) so a pattern like "Bali keeps getting
// flagged as too touristy" is queryable later. Deliberately one-shot per
// mount: once sent, the control stays in its "sent" state rather than
// allowing repeat submissions for the same view.
export function ItineraryFeedbackFlag() {
  const config = useTripConfigStore((s) => s.config)
  const [state, setState] = useState<FlagState>('idle')
  const [note, setNote] = useState('')

  async function handleSubmit() {
    setState('loading')
    try {
      await createItineraryFeedback({
        trip_config_snapshot: config as unknown as Record<string, unknown>,
        scope: 'itinerary',
        sentiment: 'missed_the_mark',
        note: note.trim() || undefined,
      })
      setState('sent')
    } catch {
      setState('error')
    }
  }

  if (state === 'sent') {
    return (
      <p className="text-xs text-[var(--_muted-fg)]">
        Thanks — we’ve logged this itinerary as a miss. It helps us improve.
      </p>
    )
  }

  if (state === 'idle') {
    return (
      <button
        type="button"
        onClick={() => setState('expanded')}
        className="text-xs font-medium text-[var(--_muted-fg)] underline decoration-dotted hover:text-[var(--_fg)]"
      >
        This itinerary missed the mark
      </button>
    )
  }

  return (
    <div className="rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-3">
      <p className="text-xs font-semibold text-[var(--_fg)]">What went wrong? (optional)</p>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="e.g. too touristy, didn't match my pace…"
        rows={2}
        maxLength={500}
        className="mt-2 w-full resize-none rounded-lg border border-[var(--_border)] bg-[var(--_bg)] p-2 text-xs text-[var(--_fg)] placeholder:text-[var(--_muted-fg)]"
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={state === 'loading'}
          className="rounded-lg bg-[var(--_primary)] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
        >
          {state === 'loading' ? 'Sending…' : 'Submit'}
        </button>
        <button
          type="button"
          onClick={() => setState('idle')}
          className="text-xs text-[var(--_muted-fg)] hover:text-[var(--_fg)]"
        >
          Cancel
        </button>
      </div>
      {state === 'error' && (
        <p className="mt-1 text-xs text-red-500">Couldn’t send that just now. Please retry.</p>
      )}
    </div>
  )
}
