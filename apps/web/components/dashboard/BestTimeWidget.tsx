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
      <div className="h-3 bg-slate-200 rounded w-1/2" />
      <div className="h-2 bg-slate-200 rounded w-3/4" />
    </div>
  )

  if (error || !data) return (
    <div className="px-4 py-3 text-xs text-slate-400 italic">
      Best-time data unavailable for this destination.
    </div>
  )

  return (
    <div className="px-4 py-3 space-y-3">
      <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
        📅 Best Time to Visit
      </h4>

      {/* Month bar */}
      <div className="flex gap-0.5">
        {MONTHS.map((m) => {
          const isBest = data.best_months?.some((bm) => bm.toLowerCase().startsWith(m.toLowerCase()))
          const isAvoid = data.avoid_months?.some((am) => am.toLowerCase().startsWith(m.toLowerCase()))
          return (
            <div key={m} className="flex-1 text-center">
              <div
                className={[
                  'h-3 rounded-sm',
                  isBest ? 'bg-green-400' : isAvoid ? 'bg-red-300' : 'bg-slate-200',
                ].join(' ')}
              />
              <span className="text-[9px] text-slate-400 mt-0.5 block">{m[0]}</span>
            </div>
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex gap-3 text-[10px] text-slate-500">
        <span><span className="inline-block w-2 h-2 bg-green-400 rounded-sm mr-1" />Best</span>
        <span><span className="inline-block w-2 h-2 bg-red-300 rounded-sm mr-1" />Avoid</span>
        <span><span className="inline-block w-2 h-2 bg-slate-200 rounded-sm mr-1" />OK</span>
      </div>

      {/* Summary */}
      {data.weather_summary && (
        <p className="text-xs text-slate-600 leading-relaxed">{data.weather_summary}</p>
      )}

      <div className="space-y-1">
        {data.peak_season && (
          <p className="text-xs text-slate-500">🎯 Peak: <span className="font-medium text-slate-700">{data.peak_season}</span></p>
        )}
        {data.off_season && (
          <p className="text-xs text-slate-500">💤 Off-season: <span className="font-medium text-slate-700">{data.off_season}</span></p>
        )}
      </div>
    </div>
  )
}
