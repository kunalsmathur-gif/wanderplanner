'use client'

import { useState } from 'react'
import { X, MapIcon, Loader2, AlertTriangle, RotateCcw } from 'lucide-react'
import { useComparisonStore } from '@/store/comparisonStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { compareDestinations } from '@/lib/api'
import { DestinationSearchInput } from './DestinationSearchInput'
import { ComparisonGrid } from './ComparisonGrid'
import type { DestinationInput } from '@/types'

interface Props {
  onClose: () => void
}

export function ComparisonPanel({ onClose }: Props) {
  const { result, status, setResult, setStatus, setDestinations } = useComparisonStore()
  const tripConfig = useTripConfigStore((s) => s.config)

  const [destA, setDestA] = useState<DestinationInput | null>(null)
  const [destB, setDestB] = useState<DestinationInput | null>(null)

  const canCompare = !!destA && !!destB && destA.city !== destB.city

  async function handleCompare() {
    if (!destA || !destB) return
    setDestinations(destA, destB)
    setStatus('loading')
    try {
      const response = await compareDestinations([destA, destB], tripConfig)
      setResult(response)
    } catch {
      setStatus('error')
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-[var(--_border)] bg-[var(--_card)] px-5 py-4">
        <div>
          <h2 className="font-semibold text-[var(--_fg)]">Compare Destinations</h2>
          <p className="mt-0.5 text-xs text-[var(--_muted-fg)]">
            AI-powered side-by-side analysis based on your trip preferences
          </p>
        </div>
        <button
          onClick={onClose}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-[var(--_muted-fg)] transition-colors hover:bg-[var(--_muted)] hover:text-[var(--_fg)]"
          aria-label="Close comparison"
          type="button"
        >
          <X size={18} />
        </button>
      </div>

      {/* Inputs */}
      <div className="shrink-0 border-b border-[var(--_border)] bg-[var(--_bg)] px-5 py-4">
        <div className="grid grid-cols-2 gap-4">
          <DestinationSearchInput label="Destination A" value={destA} onChange={setDestA} />
          <DestinationSearchInput label="Destination B" value={destB} onChange={setDestB} />
        </div>
        <button
          onClick={handleCompare}
          disabled={!canCompare || status === 'loading'}
          className={canCompare && status !== 'loading' ? 'btn btn-primary mt-3 w-full' : 'btn mt-3 w-full cursor-not-allowed opacity-40'}
        >
          {status === 'loading'
            ? <><Loader2 size={14} className="animate-spin" /> Comparing…</>
            : 'Compare destinations →'}
        </button>
        {!canCompare && destA && destB && destA.city === destB.city && (
          <p className="mt-1 text-xs text-[var(--_destructive)]">Choose two different destinations.</p>
        )}
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {status === 'idle' && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-[var(--_muted-fg)]">
            <MapIcon size={40} strokeWidth={1} />
            <p className="text-sm">Search two destinations above to compare them.</p>
          </div>
        )}

        {status === 'loading' && (
          <div className="flex h-full flex-col items-center justify-center gap-4">
            <Loader2 size={36} className="animate-spin text-[var(--_primary)]" />
            <p className="text-sm text-[var(--_muted-fg)]">Running AI comparison — this may take a moment…</p>
          </div>
        )}

        {status === 'error' && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-[var(--_muted-fg)]">
            <AlertTriangle size={36} strokeWidth={1.5} className="text-[var(--_accent)]" />
            <p className="text-sm">Comparison failed. Please try again.</p>
            <button onClick={handleCompare} className="btn btn-primary">
              <RotateCcw size={14} /> Retry
            </button>
          </div>
        )}

        {(status === 'success' || status === 'partial') && result && destA && destB && (
          <ComparisonGrid result={result} destA={destA} destB={destB} />
        )}
      </div>
    </div>
  )
}
