'use client'

import { useItineraryStore } from '@/store/itineraryStore'
import { useAppStore } from '@/store/appStore'
import { ErrorState } from '@/components/common/ErrorState'
import { formatDayDate } from '@/lib/format'

export function ItineraryOverview() {
  const { status, progress, error, days, alignmentScore } = useItineraryStore()
  const goToStep = useAppStore((s) => s.goToStep)
  const goBack = useAppStore((s) => s.goBack)

  if (status === 'loading') {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6">
        <div className="w-12 h-12 rounded-full border-4 border-[var(--_primary)] border-t-transparent animate-spin" />
        <div className="text-center">
          <p className="text-base font-semibold text-[var(--_fg)]">{progress.message || 'Building your itinerary…'}</p>
          <p className="text-sm text-[var(--_muted-fg)] mt-1">Step {progress.step} of {progress.total}</p>
        </div>
        <div className="flex gap-1">
          {Array.from({ length: progress.total }).map((_, i) => (
            <div
              key={i}
              className={[
                'h-1.5 w-8 rounded-full transition-all',
                i < progress.step ? 'bg-[var(--_primary)]' : 'bg-[var(--_muted)]',
              ].join(' ')}
            />
          ))}
        </div>
      </div>
    )
  }

  if (status === 'error' && error) {
    return (
      <ErrorState
        code={error.code}
        message={error.message}
        onRetry={() => goBack()}
        onBack={() => goBack()}
      />
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-[var(--_fg)]">Your Itinerary Overview</h1>
            <p className="text-sm text-[var(--_muted-fg)] mt-1">{days.length} days generated</p>
          </div>
          <button
            onClick={() => goBack()}
            className="text-sm text-[var(--_muted-fg)] hover:text-[var(--_fg)]"
          >
            ← Edit inputs
          </button>
        </div>

        <div className="space-y-3">
          {days.map((day) => (
            <div
              key={day.day_number}
              className="bg-[var(--_card)] border border-[var(--_border)] rounded-lg p-4"
              style={{ boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05)' }}
            >
              <div className="flex items-center gap-3 mb-2">
                <span className="w-8 h-8 rounded-full bg-[var(--_primary)] text-[var(--_on-primary)] flex items-center justify-center text-sm font-bold shrink-0">
                  {day.day_number}
                </span>
                <div>
                  <p className="font-semibold text-[var(--_fg)] text-sm">{day.theme}</p>
                  <p className="text-xs text-[var(--_muted-fg)]">{formatDayDate(day.date)} · {day.items.length} activities</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-1 pl-11">
                {day.items.slice(0, 4).map((item) => (
                  <span key={item.id} className="text-xs bg-[var(--_muted)] text-[var(--_muted-fg)] rounded px-2 py-0.5">
                    {item.title}
                  </span>
                ))}
                {day.items.length > 4 && (
                  <span className="text-xs text-[var(--_muted-fg)]">+{day.items.length - 4} more</span>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={() => goToStep(3)}
            className="flex-1 h-12 bg-[var(--_primary)] text-[var(--_on-primary)] rounded-lg font-semibold hover:bg-[var(--_primary-hover)]"
          >
            Finalize & View Detailed Itinerary →
          </button>
        </div>
      </div>
    </div>
  )
}
