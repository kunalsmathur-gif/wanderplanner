'use client'

import { useState } from 'react'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'

const CATEGORIES = [
  { key: 'flights_inr',          icon: '✈️',  label: 'Flights'             },
  { key: 'visa_inr',             icon: '🛂',  label: 'Visa & Entry'        },
  { key: 'accommodation_inr',    icon: '🏨',  label: 'Accommodation'       },
  { key: 'activities_inr',       icon: '🎟️', label: 'Activities & Passes' },
  { key: 'food_inr',             icon: '🍜',  label: 'Food & Dining'       },
  { key: 'local_transport_inr',  icon: '🚌',  label: 'Local Transport'     },
  { key: 'shopping_inr',         icon: '🛍️', label: 'Shopping & Souvenirs'},
  { key: 'emergency_buffer_inr', icon: '🆘',  label: 'Emergency Buffer'    },
] as const

type CategoryKey = typeof CATEGORIES[number]['key']

function fmtInr(n: number) {
  return `₹${n.toLocaleString('en-IN')}`
}

export function ExpenseBreakupCard() {
  const breakdown = useItineraryStore((s) => s.expenseBreakdown)
  const budget = useTripConfigStore((s) => s.config.budget)
  const [view, setView] = useState<'group' | 'person'>('group')
  const [open, setOpen] = useState(true)

  if (!breakdown || breakdown.total_inr === 0) return null

  const people = breakdown.num_people || 1
  const divisor = view === 'person' ? people : 1

  const overBudget = budget.amount > 0 && breakdown.total_inr > budget.amount
  const shortfall = breakdown.total_inr - budget.amount

  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden bg-white">
      {/* Header — collapsible */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2.5 bg-slate-50 hover:bg-slate-100 transition-colors"
      >
        <span className="text-xs font-semibold text-slate-700">💰 Expense Breakup</span>
        <span className="text-slate-400 text-xs">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="px-3 py-3 space-y-3">
          {/* Per-person / Group toggle */}
          <div className="flex rounded-lg border border-slate-200 overflow-hidden text-xs">
            {(['group', 'person'] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={[
                  'flex-1 py-1 font-medium transition-colors',
                  view === v
                    ? 'bg-[#1E40AF] text-white'
                    : 'text-slate-500 hover:bg-slate-50',
                ].join(' ')}
              >
                {v === 'group' ? `Group (${people})` : 'Per Person'}
              </button>
            ))}
          </div>

          {/* Category rows */}
          <div className="space-y-0">
            {CATEGORIES.map(({ key, icon, label }) => {
              const raw = breakdown[key as CategoryKey] as number
              if (!raw) return null
              return (
                <div
                  key={key}
                  className="flex items-center justify-between py-1.5 border-b border-slate-100 last:border-0"
                >
                  <span className="text-xs text-slate-500">{icon} {label}</span>
                  <span className="text-xs font-medium text-slate-700">
                    {fmtInr(Math.round(raw / divisor))}
                  </span>
                </div>
              )
            })}
          </div>

          {/* Total */}
          <div className="flex items-center justify-between pt-1 border-t border-slate-300">
            <span className="text-xs font-bold text-slate-800">Total</span>
            <div className="text-right">
              <p className="text-sm font-bold text-[#0F172A]">
                {fmtInr(Math.round(breakdown.total_inr / divisor))}
              </p>
              {breakdown.destination_currency_code && breakdown.total_destination_currency > 0 && (
                <p className="text-xs text-slate-400">
                  ≈ {breakdown.destination_currency_code}{' '}
                  {Math.round(breakdown.total_destination_currency / divisor).toLocaleString()}
                </p>
              )}
            </div>
          </div>

          {/* Budget warning */}
          {overBudget && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-2.5 py-2 text-xs text-red-700">
              ⚠️ Estimate exceeds your budget by{' '}
              <strong>{fmtInr(shortfall)}</strong>. Consider adjusting dates or accommodation.
            </div>
          )}
          {!overBudget && budget.amount > 0 && (
            <div className="bg-green-50 border border-green-200 rounded-lg px-2.5 py-2 text-xs text-green-700">
              ✅ Within budget — buffer of{' '}
              <strong>{fmtInr(budget.amount - breakdown.total_inr)}</strong>
            </div>
          )}

          <p className="text-xs text-slate-400 italic">
            Estimates are approximate and based on average market rates.
          </p>
        </div>
      )}
    </div>
  )
}
