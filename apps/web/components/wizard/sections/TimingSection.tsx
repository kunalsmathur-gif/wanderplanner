'use client'

import { useTripConfigStore } from '@/store/tripConfigStore'

export function TimingSection() {
  const dates = useTripConfigStore((s) => s.config.dates)
  const updateDates = useTripConfigStore((s) => s.updateDates)

  return (
    <section className="space-y-3">
      <h2 className="text-base font-semibold text-[#0F172A]">Timing *</h2>
      <div className="flex gap-3 mb-3">
        {(['fixed', 'flexible'] as const).map((mode) => {
          const isFixed = mode === 'fixed'
          const active = isFixed ? !dates.flexible : dates.flexible
          return (
            <button
              key={mode}
              onClick={() => updateDates({ flexible: !isFixed })}
              className={[
                'px-4 py-2 rounded-lg border text-sm font-medium transition-all',
                active
                  ? 'bg-[#1E40AF] border-[#1E40AF] text-white'
                  : 'bg-white border-slate-300 text-slate-700 hover:border-[#1E40AF]',
              ].join(' ')}
            >
              {isFixed ? '📅 Fixed Dates' : '🗓️ Flexible'}
            </button>
          )
        })}
      </div>

      {!dates.flexible ? (
        <div className="flex gap-4">
          <div className="flex-1">
            <label className="block text-xs text-slate-500 mb-1">Start date</label>
            <input
              type="date"
              value={dates.start ?? ''}
              onChange={(e) => updateDates({ start: e.target.value || null })}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1E40AF]"
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs text-slate-500 mb-1">End date</label>
            <input
              type="date"
              value={dates.end ?? ''}
              onChange={(e) => updateDates({ end: e.target.value || null })}
              min={dates.start ?? undefined}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1E40AF]"
            />
          </div>
        </div>
      ) : (
        <div>
          <label className="block text-xs text-slate-500 mb-1">Preferred month or season</label>
          <input
            type="text"
            placeholder="e.g. November 2026, Summer 2027"
            value={dates.season ?? ''}
            onChange={(e) => updateDates({ season: e.target.value })}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1E40AF]"
          />
        </div>
      )}
    </section>
  )
}
