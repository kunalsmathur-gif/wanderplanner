'use client'

import { useState } from 'react'
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
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 bg-white shrink-0">
        <div>
          <h2 className="font-semibold text-[#0F172A]">Compare Destinations</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Side-by-side analysis based on your trip preferences
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-700 text-lg leading-none"
          aria-label="Close comparison"
          type="button"
        >
          ✕
        </button>
      </div>

      {/* Inputs */}
      <div className="px-5 py-4 border-b border-slate-200 bg-slate-50 shrink-0">
        <div className="grid grid-cols-2 gap-4">
          <DestinationSearchInput
            label="Destination A"
            value={destA}
            onChange={setDestA}
          />
          <DestinationSearchInput
            label="Destination B"
            value={destB}
            onChange={setDestB}
          />
        </div>
        <button
          onClick={handleCompare}
          disabled={!canCompare || status === 'loading'}
          className={[
            'mt-3 w-full h-10 rounded-lg text-sm font-semibold transition-all',
            canCompare && status !== 'loading'
              ? 'bg-[#1E40AF] text-white hover:bg-blue-800'
              : 'bg-slate-200 text-slate-400 cursor-not-allowed',
          ].join(' ')}
        >
          {status === 'loading' ? 'Comparing…' : 'Compare →'}
        </button>
        {!canCompare && destA && destB && destA.city === destB.city && (
          <p className="text-xs text-red-500 mt-1">Choose two different destinations.</p>
        )}
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {status === 'idle' && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-400">
            <span className="text-4xl">🗺️</span>
            <p className="text-sm">Search two destinations above to compare them.</p>
          </div>
        )}

        {status === 'loading' && (
          <div className="flex flex-col items-center justify-center h-full gap-4">
            <div className="w-10 h-10 rounded-full border-4 border-[#1E40AF] border-t-transparent animate-spin" />
            <p className="text-sm text-slate-500">Fetching comparison data…</p>
          </div>
        )}

        {status === 'error' && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-500">
            <span className="text-4xl">⚠️</span>
            <p className="text-sm">Comparison failed. Please try again.</p>
            <button
              onClick={handleCompare}
              className="px-4 py-2 bg-[#1E40AF] text-white rounded-lg text-sm hover:bg-blue-800"
            >
              Retry
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
