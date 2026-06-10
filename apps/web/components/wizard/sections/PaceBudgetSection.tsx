'use client'

import { useTripConfigStore } from '@/store/tripConfigStore'

const PACES = [
  { id: 'relaxed', label: '😌 Relaxed', desc: '3–4 activities/day' },
  { id: 'moderate', label: '🚶 Moderate', desc: '4–5 activities/day' },
  { id: 'packed', label: '⚡ Packed', desc: '5–6 activities/day' },
] as const

const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR', 'AUD', 'SGD', 'MYR', 'AED']

export function PaceBudgetSection() {
  const config = useTripConfigStore((s) => s.config)
  const updateConfig = useTripConfigStore((s) => s.updateConfig)
  const updateBudget = useTripConfigStore((s) => s.updateBudget)
  const effectivePace = useTripConfigStore((s) => s.effectivePace)

  const activePace = effectivePace()
  const autoOverride = activePace !== config.pace

  return (
    <section className="space-y-4">
      <h2 className="text-base font-semibold text-[#0F172A]">Pace & Budget *</h2>

      <div>
        <label className="block text-xs text-slate-500 mb-2">Itinerary pace</label>
        <div className="flex gap-3">
          {PACES.map((p) => (
            <button
              key={p.id}
              onClick={() => updateConfig({ pace: p.id })}
              className={[
                'flex-1 px-3 py-3 rounded-lg border text-center transition-all',
                activePace === p.id
                  ? 'bg-[#1E40AF] border-[#1E40AF] text-white'
                  : 'bg-white border-slate-300 text-slate-700 hover:border-[#1E40AF]',
              ].join(' ')}
            >
              <div className="text-sm font-medium">{p.label}</div>
              <div className={`text-xs mt-0.5 ${activePace === p.id ? 'text-blue-200' : 'text-slate-400'}`}>
                {p.desc}
              </div>
            </button>
          ))}
        </div>
        {autoOverride && (
          <p className="mt-2 text-xs text-[#047857]">
            ✓ Pace overridden to Relaxed — group includes children under 5.
          </p>
        )}
      </div>

      <div>
        <label className="block text-xs text-slate-500 mb-2">Total group budget *</label>
        <div className="flex gap-2">
          <select
            value={config.budget.currency}
            onChange={(e) => updateBudget({ currency: e.target.value })}
            className="border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1E40AF] bg-white"
          >
            {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
          </select>
          <input
            type="number"
            min={0}
            placeholder="e.g. 150000"
            value={config.budget.amount || ''}
            onChange={(e) => updateBudget({ amount: Number(e.target.value) })}
            className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1E40AF]"
          />
        </div>
        <p className="mt-1 text-xs text-slate-400">
          All-inclusive: accommodation, activities, local transport.
          International flights are separate.
        </p>
      </div>
    </section>
  )
}
