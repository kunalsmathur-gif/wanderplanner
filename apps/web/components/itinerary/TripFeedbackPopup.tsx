'use client'

import { useEffect } from 'react'
import { X } from 'lucide-react'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useItineraryFeedbackStore } from '@/store/itineraryFeedbackStore'
import { useFeedbackPromptStore } from '@/store/feedbackPromptStore'

// Dismissible feedback popup surfaced on key "leaving/acting on this
// itinerary" moments (Edit Trip, Generate/regenerate, Get Quotation, Share
// — see the trigger call sites in those components). Rendered once at the
// dashboard root so it can float above whichever panel triggered it.
export function TripFeedbackPopup() {
  const open = useFeedbackPromptStore((s) => s.open)
  const dismiss = useFeedbackPromptStore((s) => s.dismiss)
  const markInteracted = useFeedbackPromptStore((s) => s.markInteracted)
  const config = useTripConfigStore((s) => s.config)
  const hasItinerary = useItineraryStore((s) => s.days.length > 0)
  const { state, vote, note, setNote, thumbsUp, thumbsDown, submitNote, skipNote, cancelNote, retry } =
    useItineraryFeedbackStore()

  const snapshot = config as unknown as Record<string, unknown>

  // Auto-dismiss a short beat after a successful submission so it doesn't
  // linger on screen once its job is done.
  useEffect(() => {
    if (state !== 'sent') return
    const t = setTimeout(() => markInteracted(), 1600)
    return () => clearTimeout(t)
  }, [state, markInteracted])

  if (!open || !hasItinerary) return null

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-label="Itinerary feedback"
      className="fixed bottom-4 right-4 z-50 w-[calc(100vw-2rem)] max-w-sm rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-4 shadow-xl"
    >
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss"
        className="absolute right-3 top-3 rounded-lg p-1 text-[var(--_muted-fg)] hover:bg-[var(--_muted)] hover:text-[var(--_fg)]"
      >
        <X size={16} />
      </button>

      {state === 'sent' ? (
        <p className="pr-6 text-sm font-medium text-[var(--_fg)]">
          {vote === 'thumbs_up'
            ? '👍 Thanks — glad this itinerary worked for you!'
            : '👎 Thanks for the feedback — it helps us improve.'}
        </p>
      ) : (
        <>
          <p className="pr-6 text-sm font-semibold text-[var(--_fg)]">
            Did you find the trip recommendations helpful?
          </p>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => thumbsUp(snapshot)}
              disabled={state === 'loading'}
              aria-label="Yes, helpful"
              className="btn btn-outline flex-1 disabled:opacity-50"
            >
              👍 Yes
            </button>
            <button
              type="button"
              onClick={thumbsDown}
              disabled={state === 'loading'}
              aria-label="No, not helpful"
              className="btn btn-outline flex-1 disabled:opacity-50"
            >
              👎 No
            </button>
          </div>

          {state === 'awaiting_note' && (
            <div className="mt-3 space-y-2">
              <p className="text-xs font-semibold text-[var(--_fg)]">What went wrong? (optional)</p>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="e.g. too touristy, didn't match my pace…"
                rows={2}
                maxLength={500}
                autoFocus
                className="w-full resize-none rounded-lg border border-[var(--_border)] bg-[var(--_bg)] p-2 text-xs text-[var(--_fg)] placeholder:text-[var(--_muted-fg)]"
              />
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => submitNote(snapshot)}
                  className="rounded-lg bg-[var(--_primary)] px-3 py-1.5 text-xs font-semibold text-white"
                >
                  Submit
                </button>
                <button
                  type="button"
                  onClick={() => skipNote(snapshot)}
                  className="text-xs text-[var(--_muted-fg)] hover:text-[var(--_fg)]"
                >
                  Skip
                </button>
                <button
                  type="button"
                  onClick={cancelNote}
                  className="text-xs text-[var(--_muted-fg)] hover:text-[var(--_fg)]"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {state === 'error' && (
            <div className="mt-2 flex items-center gap-2 text-xs text-red-500">
              Couldn’t send that just now.
              <button type="button" onClick={retry} className="font-medium underline">
                Retry
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
