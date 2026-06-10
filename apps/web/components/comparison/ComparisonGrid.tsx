'use client'

import type { ComparisonResponse, DestinationInput } from '@/types'

interface Props {
  result: ComparisonResponse
  destA: DestinationInput
  destB: DestinationInput
}

const ICONS: Record<string, string> = {
  weather: '🌤',
  budget: '💶',
  visa: '🛂',
  travel_time: '✈️',
  best_season: '📅',
  safety: '🛡️',
  connectivity: '📶',
  language: '🗣️',
}

export function ComparisonGrid({ result, destA, destB }: Props) {
  return (
    <div className="w-full overflow-x-auto">
      {result.partial_failures.length > 0 && (
        <div className="mb-3 flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5">
          <span className="text-amber-500 shrink-0 mt-0.5">⚠</span>
          <p className="text-xs text-amber-700">
            Partial data: {result.partial_failures.join(', ')} could not be fetched.
            Results shown are based on available data.
          </p>
        </div>
      )}

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b-2 border-slate-200">
            <th className="py-3 px-4 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide w-[28%]">
              Parameter
            </th>
            <th className="py-3 px-4 text-center text-xs font-semibold text-[#1E40AF] uppercase tracking-wide w-[30%]">
              {destA.city}
            </th>
            <th className="py-3 px-4 text-center text-xs font-semibold text-slate-700 uppercase tracking-wide w-[30%]">
              {destB.city}
            </th>
            <th className="py-3 px-4 text-center text-xs font-semibold text-slate-500 uppercase tracking-wide w-[12%]">
              Winner
            </th>
          </tr>
        </thead>
        <tbody>
          {result.comparison.map((row, idx) => {
            const isEven = idx % 2 === 0
            const aWins = row.winner === destA.city
            const bWins = row.winner === destB.city
            const icon = ICONS[row.parameter.toLowerCase().replace(/ /g, '_')] ?? '📊'

            return (
              <tr
                key={row.parameter}
                className={isEven ? 'bg-white' : 'bg-slate-50'}
              >
                <td className="py-3 px-4 font-medium text-slate-700">
                  <span className="mr-1.5">{icon}</span>
                  {row.parameter}
                  {row.unit ? <span className="text-slate-400 text-xs ml-1">({row.unit})</span> : null}
                </td>
                <td className={[
                  'py-3 px-4 text-center font-medium',
                  aWins ? 'text-green-700 bg-green-50' : 'text-slate-700',
                ].join(' ')}>
                  {String(row.values[destA.city] ?? '—')}
                  {aWins && <span className="ml-1 text-green-500">✓</span>}
                </td>
                <td className={[
                  'py-3 px-4 text-center font-medium',
                  bWins ? 'text-green-700 bg-green-50' : 'text-slate-700',
                ].join(' ')}>
                  {String(row.values[destB.city] ?? '—')}
                  {bWins && <span className="ml-1 text-green-500">✓</span>}
                </td>
                <td className="py-3 px-4 text-center">
                  {row.winner ? (
                    <span className="inline-block bg-green-100 text-green-700 text-xs font-semibold px-2 py-0.5 rounded-full">
                      {row.winner}
                    </span>
                  ) : (
                    <span className="text-slate-400 text-xs">Tie</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {result.comparison.length > 0 && (
        <div className="mt-4 px-4 py-3 bg-blue-50 border border-blue-200 rounded-lg">
          <p className="text-xs text-blue-700">
            <span className="font-semibold">💡 Insight:</span>{' '}
            {(() => {
              const wins: Record<string, number> = {}
              result.comparison.forEach((r) => {
                if (r.winner) wins[r.winner] = (wins[r.winner] ?? 0) + 1
              })
              const [topDest, count] = Object.entries(wins).sort((a, b) => b[1] - a[1])[0] ?? []
              if (!topDest) return 'Both destinations are comparable — your call!'
              return `${topDest} wins ${count} of ${result.comparison.length} parameters.`
            })()}
          </p>
        </div>
      )}
    </div>
  )
}
