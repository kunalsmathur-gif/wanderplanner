'use client'

import { useEffect, useState } from 'react'
import { getBestTime } from '@/lib/api'

interface BestTimeData {
  destination: string
  best_months: string[]
  avoid_months: string[]
  peak_season: string
  off_season: string
  weather_summary: string
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

interface Props {
  destination: string
}

export function BestTimeWidget({ destination }: Props) {
  const [data, setData] = useState<BestTimeData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!destination) return
    setLoading(true)
    setError(false)
    getBestTime(destination)
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [destination])

  if (loading) return (
    <div className="animate-pulse space-y-2 px-4 py-3">
      <div className="h-3 bg-[var(--_muted)] rounded w-1/2" />
      <div className="h-2 bg-[var(--_muted)] rounded w-3/4" />
    </div>
  )

  if (error || !data) return (
    <div className="px-4 py-3 text-xs text-[var(--_muted-fg)] italic">
      Best-time data unavailable for this destination.
    </div>
  )

  return (
    <div className="px-4 py-3 space-y-3">
      <h4 className="text-xs font-semibold text-[var(--_muted-fg)] uppercase tracking-wide">
        📅 Best Time to Visit
      </h4>

      {/* Month bar */}
      <div className="flex gap-0.5">
        {MONTHS.map((m) => {
          const isBest = data.best_months?.some((bm) => bm.toLowerCase().startsWith(m.toLowerCase()))
          const isAvoid = data.avoid_months?.some((am) => am.toLowerCase().startsWith(m.toLowerCase()))
          const statusLabel = isBest ? 'Best' : isAvoid ? 'Avoid' : 'OK'
          const statusCue = isBest ? '✓' : isAvoid ? '!' : '–'
          return (
            <div key={m} className="flex-1 text-center">
              <div
                aria-label={`${m}: ${statusLabel}`}
                title={`${m}: ${statusLabel}`}
                className={[
                  'flex h-5 items-center justify-center rounded-sm text-xs font-semibold',
                  isBest ? 'bg-green-400' : isAvoid ? 'bg-red-300' : 'bg-[var(--_muted)]',
                ].join(' ')}
              >
                {statusCue}
              </div>
              <span className="mt-0.5 block text-xs text-[var(--_muted-fg)]">{m[0]}</span>
            </div>
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 text-xs text-[var(--_muted-fg)]">
        <span><span className="mr-1 inline-flex h-4 w-4 items-center justify-center rounded-sm bg-green-400 text-[10px] font-semibold text-[var(--_fg)]">✓</span>Best</span>
        <span><span className="mr-1 inline-flex h-4 w-4 items-center justify-center rounded-sm bg-red-300 text-[10px] font-semibold text-[var(--_fg)]">!</span>Avoid</span>
        <span><span className="mr-1 inline-flex h-4 w-4 items-center justify-center rounded-sm bg-[var(--_muted)] text-[10px] font-semibold text-[var(--_fg)]">–</span>OK</span>
      </div>

      {/* Summary */}
      {data.weather_summary && (
        <p className="text-xs text-[var(--_fg-muted)] leading-relaxed">{data.weather_summary}</p>
      )}

      <div className="space-y-1">
        {data.peak_season && (
          <p className="text-xs text-[var(--_muted-fg)]">👥 Busiest (crowds & prices): <span className="font-medium text-[var(--_fg)]">{data.peak_season}</span></p>
        )}
        {data.off_season && (
          <p className="text-xs text-[var(--_muted-fg)]">💤 Quietest: <span className="font-medium text-[var(--_fg)]">{data.off_season}</span></p>
        )}
      </div>
    </div>
  )
}
