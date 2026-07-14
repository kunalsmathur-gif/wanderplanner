'use client'

import { useEffect, useState } from 'react'

interface Rates {
  [currency: string]: number
}

const TRACKED = ['USD', 'EUR', 'GBP', 'JPY', 'AED', 'SGD', 'THB', 'AUD']

interface Props {
  baseCurrency: string
}

export function CurrencyWidget({ baseCurrency }: Props) {
  const [rates, setRates] = useState<Rates | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!baseCurrency) return
    setLoading(true)
    setError(false)
    fetch(`https://api.frankfurter.app/latest?from=${baseCurrency}`)
      .then((r) => r.json())
      .then((d) => setRates(d.rates))
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [baseCurrency])

  if (loading) return (
    <div className="animate-pulse px-4 py-3 space-y-1.5">
      {[1, 2, 3].map((i) => <div key={i} className="h-3 bg-[var(--_muted)] rounded w-full" />)}
    </div>
  )

  if (error) return (
    <div className="px-4 py-2 text-xs text-[var(--_muted-fg)] italic">
      Rates temporarily unavailable.
    </div>
  )

  const display = TRACKED.filter((c) => c !== baseCurrency && rates?.[c])

  if (!display.length) return null

  return (
    <div className="px-4 py-3 space-y-2">
      <h4 className="text-xs font-semibold text-[var(--_muted-fg)] uppercase tracking-wide">
        💱 Exchange Rates
      </h4>
      <p className="text-[10px] text-[var(--_muted-fg)]">1 {baseCurrency} =</p>
      <div className="space-y-1">
        {display.slice(0, 6).map((cur) => (
          <div key={cur} className="flex justify-between text-xs">
            <span className="text-[var(--_muted-fg)]">{cur}</span>
            <span className="font-medium text-[var(--_fg)]">{rates![cur].toFixed(4)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
