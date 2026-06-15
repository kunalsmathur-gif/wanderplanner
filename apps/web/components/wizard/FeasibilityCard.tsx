'use client'

import { useEffect, useRef, useState } from 'react'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { checkFeasibility } from '@/lib/api'
import type { FeasibilityResponse } from '@/types'

function fmt(n: number) {
  return `₹${n.toLocaleString('en-IN')}`
}

export function FeasibilityCard() {
  const config = useTripConfigStore((s) => s.config)
  const [result, setResult] = useState<FeasibilityResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Only run when destination + dates + budget are all set
  const dest = config.destination?.city
  const start = config.dates.start
  const budget = config.budget.amount

  const canCheck = Boolean(dest && (start || config.dates.flexible) && budget > 0)

  useEffect(() => {
    if (!canCheck) {
      setResult(null)
      return
    }
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      setError(false)
      try {
        const data = await checkFeasibility(config)
        setResult(data)
      } catch {
        setError(true)
      } finally {
        setLoading(false)
      }
    }, 1200)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [dest, start, config.dates.flexible, budget, config.accommodation.style.join(',')])

  if (!canCheck) return null

  if (loading) {
    return (
      <div className="border border-slate-200 rounded-lg p-4 flex items-center gap-3 bg-slate-50">
        <div className="w-4 h-4 border-2 border-[#1E40AF] border-t-transparent rounded-full animate-spin shrink-0" />
        <p className="text-sm text-slate-500">Checking budget feasibility…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="border border-amber-200 rounded-lg p-4 bg-amber-50 text-sm text-amber-700">
        ⚠️ Could not fetch cost estimate. Proceed with caution.
      </div>
    )
  }

  if (!result) return null

  const { feasible, verdict, breakdown, shortfall_inr, buffer_inr, alternatives, disclaimer } = result

  return (
    <div
      className={[
        'border rounded-lg p-4 space-y-3',
        feasible
          ? 'border-green-200 bg-green-50'
          : 'border-red-200 bg-red-50',
      ].join(' ')}
    >
      {/* Verdict */}
      <p className={`text-sm font-semibold ${feasible ? 'text-green-800' : 'text-red-800'}`}>
        {verdict}
      </p>

      {/* Cost breakdown */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <span className="text-slate-500">✈️ Flights (round-trip)</span>
        <span className="text-right font-medium text-slate-700">{fmt(breakdown.flights_inr)}</span>
        <span className="text-slate-500">🛂 Visa fees</span>
        <span className="text-right font-medium text-slate-700">{fmt(breakdown.visa_inr)}</span>
        <span className="text-slate-500">🏨 Accommodation</span>
        <span className="text-right font-medium text-slate-700">{fmt(breakdown.accommodation_inr)}</span>
        <span className="text-slate-500">🍜 Daily expenses</span>
        <span className="text-right font-medium text-slate-700">{fmt(breakdown.daily_expenses_inr)}</span>
        <span className="font-semibold text-slate-700 pt-1 border-t border-slate-200">Total estimate</span>
        <span className={`text-right font-bold pt-1 border-t border-slate-200 ${feasible ? 'text-green-700' : 'text-red-700'}`}>
          {fmt(breakdown.total_estimated_inr)}
        </span>
      </div>

      {/* Buffer or shortfall */}
      {feasible && buffer_inr > 0 && (
        <p className="text-xs text-green-700">
          🟢 Remaining budget: <strong>{fmt(buffer_inr)}</strong> for emergencies & extras
        </p>
      )}
      {!feasible && shortfall_inr > 0 && (
        <p className="text-xs text-red-700">
          🔴 Budget short by <strong>{fmt(shortfall_inr)}</strong>
        </p>
      )}

      {/* Alternatives */}
      {alternatives.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-slate-600 mb-1.5">
            {feasible ? '💡 Similar destinations to consider:' : '💡 Destinations that fit your budget:'}
          </p>
          <div className="space-y-2">
            {alternatives.map((alt) => (
              <div
                key={alt.city}
                className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs"
              >
                <div className="flex justify-between items-start">
                  <span className="font-semibold text-slate-700">{alt.city}, {alt.country}</span>
                  <span className="text-[#047857] font-semibold">{fmt(alt.estimated_total_inr)}</span>
                </div>
                <p className="text-slate-500 mt-0.5">{alt.why_cheaper}</p>
                {alt.similar_experiences.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {alt.similar_experiences.map((exp) => (
                      <span key={exp} className="bg-slate-100 text-slate-600 rounded px-1.5 py-0.5">{exp}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-xs text-slate-400 italic">{disclaimer}</p>
    </div>
  )
}
