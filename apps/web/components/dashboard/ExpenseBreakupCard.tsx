'use client'

import { useState } from 'react'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { formatCurrency } from '@/lib/format'

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
  return formatCurrency(n, 'INR')
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
    <div className="border border-[var(--_border)] rounded-lg overflow-hidden bg-[var(--_card)]">
      {/* Header — collapsible */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2.5 bg-[var(--_muted)] hover:bg-[var(--_border)]/40 transition-colors"
      >
        <span className="text-xs font-semibold text-[var(--_fg)]">💰 Expense Breakup</span>
        <span className="text-[var(--_muted-fg)] text-xs">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="px-3 py-3 space-y-3">
          {/* Per-person / Group toggle */}
          <div className="flex rounded-lg border border-[var(--_border)] overflow-hidden text-xs">
            {(['group', 'person'] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={[
                  'flex-1 py-1 font-medium transition-colors',
                  view === v
                    ? 'bg-[var(--_primary)] text-[var(--_on-primary)]'
                    : 'text-[var(--_muted-fg)] hover:bg-[var(--_muted)]',
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
                  className="flex items-center justify-between py-1.5 border-b border-[var(--_border)]/50 last:border-0"
                >
                  <span className="text-xs text-[var(--_muted-fg)]">{icon} {label}</span>
                  <span className="text-xs font-medium text-[var(--_fg)]">
                    {fmtInr(Math.round(raw / divisor))}
                  </span>
                </div>
              )
            })}
          </div>

          {/* Total */}
          <div className="flex items-center justify-between pt-1 border-t border-[var(--_border)]">
            <span className="text-xs font-bold text-[var(--_fg)]">Total</span>
            <div className="text-right">
              <p className="text-sm font-bold text-[var(--_fg)]">
                {fmtInr(Math.round(breakdown.total_inr / divisor))}
              </p>
              {breakdown.destination_currency_code && breakdown.total_destination_currency > 0 && (
                <p className="text-xs text-[var(--_muted-fg)]">
                  ≈ {breakdown.destination_currency_code}{' '}
                  {Math.round(breakdown.total_destination_currency / divisor).toLocaleString('en-IN')}
                </p>
              )}
            </div>
          </div>

          {/* Budget warning */}
          {overBudget && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-2.5 py-2 text-xs text-red-700 dark:bg-red-950/30 dark:border-red-800/40 dark:text-red-400">
              ⚠️ Estimate exceeds your budget by{' '}
              <strong>{fmtInr(shortfall)}</strong>. Consider adjusting dates or accommodation.
            </div>
          )}
          {!overBudget && budget.amount > 0 && (
            <div className="bg-green-50 border border-green-200 rounded-lg px-2.5 py-2 text-xs text-green-700 dark:bg-green-950/30 dark:border-green-800/40 dark:text-green-400">
              ✅ Within budget — buffer of{' '}
              <strong>{fmtInr(budget.amount - breakdown.total_inr)}</strong>
            </div>
          )}

          <p className="text-xs text-[var(--_muted-fg)] italic">
            Estimates are approximate and based on average market rates.
          </p>
        </div>
      )}
    </div>
  )
}
