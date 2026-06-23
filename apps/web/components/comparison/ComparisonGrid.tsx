'use client'

import type { ComparisonResponse, DestinationInput } from '@/types'

interface Props {
  result: ComparisonResponse
  destA: DestinationInput
  destB: DestinationInput
}

export function ComparisonGrid({ result, destA, destB }: Props) {
  return (
    <div className="w-full overflow-x-auto">
      {result.partial_failures.length > 0 && (
        <div className="mb-3 flex items-start gap-2 rounded-xl border border-[var(--_accent)]/30 bg-[var(--_accent)]/8 px-4 py-2.5">
          <span className="mt-0.5 shrink-0 text-[var(--_accent)]">⚠</span>
          <p className="text-xs text-[var(--_fg)]">
            Partial data: {result.partial_failures.join(', ')} could not be fetched.
          </p>
        </div>
      )}

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b-2 border-[var(--_border)]">
            <th className="w-[28%] px-3 py-3 text-left text-xs font-semibold uppercase tracking-widest text-[var(--_muted-fg)]">
              Parameter
            </th>
            <th className="w-[30%] px-3 py-3 text-center text-xs font-semibold uppercase tracking-widest text-[var(--_primary)]">
              {destA.city}
            </th>
            <th className="w-[30%] px-3 py-3 text-center text-xs font-semibold uppercase tracking-widest text-[var(--_fg)]">
              {destB.city}
            </th>
            <th className="w-[12%] px-3 py-3 text-center text-xs font-semibold uppercase tracking-widest text-[var(--_muted-fg)]">
              Better for you
            </th>
          </tr>
        </thead>
        <tbody>
          {result.comparison.map((row, idx) => {
            const isEven = idx % 2 === 0
            const aWins = row.winner === destA.city
            const bWins = row.winner === destB.city

            return (
              <tr
                key={row.parameter}
                className={isEven ? 'bg-[var(--_card)]' : 'bg-[var(--_bg)]'}
              >
                <td className="px-3 py-3 font-medium text-[var(--_fg)]">
                  {row.parameter}
                  {row.unit && <span className="ml-1 text-xs text-[var(--_muted-fg)]">({row.unit})</span>}
                </td>
                <td className={[
                  'px-3 py-3 text-center text-sm',
                  aWins
                    ? 'font-semibold text-[var(--_success)]'
                    : 'text-[var(--_fg)]',
                ].join(' ')}>
                  {String(row.values[destA.city] ?? '—')}
                  {aWins && <span className="ml-1 text-[var(--_success)]">✓</span>}
                </td>
                <td className={[
                  'px-3 py-3 text-center text-sm',
                  bWins
                    ? 'font-semibold text-[var(--_success)]'
                    : 'text-[var(--_fg)]',
                ].join(' ')}>
                  {String(row.values[destB.city] ?? '—')}
                  {bWins && <span className="ml-1 text-[var(--_success)]">✓</span>}
                </td>
                <td className="px-3 py-3 text-center">
                  {row.winner ? (
                    <span className="inline-block rounded-full bg-[var(--_success)]/15 px-2 py-0.5 text-xs font-semibold text-[var(--_success)]">
                      {row.winner}
                    </span>
                  ) : (
                    <span className="text-xs text-[var(--_muted-fg)]">Tie</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {result.comparison.length > 0 && (
        <div className="mt-4 rounded-xl border border-[var(--_primary)]/30 bg-[var(--_primary)]/8 px-4 py-3">
          <p className="text-xs text-[var(--_fg)]">
            <span className="font-semibold text-[var(--_primary)]">Insight: </span>
            {(() => {
              const wins: Record<string, number> = {}
              result.comparison.forEach((r) => {
                if (r.winner) wins[r.winner] = (wins[r.winner] ?? 0) + 1
              })
              const sorted = Object.entries(wins).sort((a, b) => b[1] - a[1])
              const [topDest, count] = sorted[0] ?? []
              if (!topDest) return 'Both destinations are comparable — your call!'
              return `${topDest} wins ${count} of ${result.comparison.length} parameters for your trip profile.`
            })()}
          </p>
        </div>
      )}
    </div>
  )
}
