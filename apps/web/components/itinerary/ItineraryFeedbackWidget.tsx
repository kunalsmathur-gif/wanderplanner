'use client'

import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryFeedbackStore } from '@/store/itineraryFeedbackStore'

// Itinerary-wide (not per-item) thumbs up/down — replaces the old per-place
// reaction buttons and the text-only "missed the mark" link. One vote per
// generated itinerary, shown persistently in the centre section.
export function ItineraryFeedbackWidget() {
  const config = useTripConfigStore((s) => s.config)
  const { state, vote, note, setNote, thumbsUp, thumbsDown, submitNote, skipNote, cancelNote, retry } =
    useItineraryFeedbackStore()

  const snapshot = config as unknown as Record<string, unknown>

  if (state === 'sent') {
    return (
      <div className="rounded-xl border border-[var(--_border)] bg-[var(--_card)] px-3 py-2.5 text-xs text-[var(--_muted-fg)]">
        {vote === 'thumbs_up'
          ? '👍 Thanks — glad this itinerary worked for you!'
          : '👎 Thanks for the feedback — it helps us improve.'}
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-[var(--_border)] bg-[var(--_card)] px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-[var(--_fg)]">Was this itinerary helpful?</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => thumbsUp(snapshot)}
            disabled={state === 'loading'}
            aria-label="This itinerary was helpful"
            aria-pressed={vote === 'thumbs_up'}
            className="rounded-lg px-2 py-1 text-base transition-colors hover:bg-[var(--_muted)] disabled:opacity-50"
          >
            👍
          </button>
          <button
            type="button"
            onClick={thumbsDown}
            disabled={state === 'loading'}
            aria-label="This itinerary missed the mark"
            aria-pressed={vote === 'thumbs_down'}
            className="rounded-lg px-2 py-1 text-base transition-colors hover:bg-[var(--_muted)] disabled:opacity-50"
          >
            👎
          </button>
        </div>
      </div>

      {state === 'awaiting_note' && (
        <div className="mt-2 space-y-2">
          <p className="text-xs font-semibold text-[var(--_fg)]">What went wrong? (optional)</p>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. too touristy, didn't match my pace…"
            rows={2}
            maxLength={500}
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
    </div>
  )
}
