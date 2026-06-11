'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useItineraryStore } from '@/store/itineraryStore'
import { useAppStore } from '@/store/appStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { MOCK_DAYS } from './mockData'

type Target = '1' | '2' | '3'

export default function DevPage({
  searchParams,
}: {
  searchParams: Promise<{ step?: string }>
}) {
  const router = useRouter()
  const setDays = useItineraryStore((s) => s.setDays)
  const setStatus = useItineraryStore((s) => s.setStatus)
  const goToStep = useAppStore((s) => s.goToStep)
  const setDestination = useTripConfigStore((s) => s.setDestination)
  const updateConfig = useTripConfigStore((s) => s.updateConfig)
  const updateBudget = useTripConfigStore((s) => s.updateBudget)

  useEffect(() => {
    // Inject mock data into all stores
    setDestination({ city: 'Tokyo', country: 'JP', lat: 35.6762, lon: 139.6503 })
    updateConfig({
      purpose: 'explore',
      personas: ['adventure_seeker', 'foodie'],
      pace: 'moderate',
    })
    updateBudget({ amount: 150000, currency: 'INR' })
    setDays(MOCK_DAYS, 87)
    setStatus('success')
  }, [setDays, setStatus, setDestination, updateConfig, updateBudget])

  function go(step: Target) {
    goToStep(parseInt(step) as 1 | 2 | 3)
    router.push('/')
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-lg p-10 max-w-md w-full">
        <div className="text-center mb-8">
          <p className="text-2xl font-bold text-[#1E40AF]">✈ WanderPlan</p>
          <p className="text-sm text-slate-500 mt-1">Dev Preview — Tokyo 3-day itinerary pre-loaded</p>
        </div>

        <div className="space-y-3">
          <PreviewButton
            step="1"
            label="Step 1 — Onboarding Wizard"
            desc="All inputs, 7 sections, pace & budget"
            onClick={() => go('1')}
          />
          <PreviewButton
            step="2"
            label="Step 2 — Itinerary Overview"
            desc="Day cards, finalize CTA, error states"
            onClick={() => go('2')}
          />
          <PreviewButton
            step="3"
            label="Step 3 — Detailed Itinerary"
            desc="3-column: metrics · timeline · map+social"
            onClick={() => go('3')}
          />
        </div>

        <div className="mt-8 pt-6 border-t border-slate-100">
          <p className="text-xs text-slate-400 font-semibold uppercase tracking-wide mb-3">Step 3 sub-views</p>
          <div className="space-y-2">
            <SubViewButton label="🗺️ Compare Destinations panel" onClick={() => {
              useAppStore.getState().goToStep(3)
              useAppStore.getState().setStep3View('comparison')
              router.push('/')
            }} />
          </div>
        </div>

        <p className="text-xs text-slate-400 text-center mt-6">
          This page is for local development only.
        </p>
      </div>
    </div>
  )
}

function PreviewButton({ step, label, desc, onClick }: {
  step: string; label: string; desc: string; onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left px-4 py-3 rounded-xl border-2 border-slate-200 hover:border-[#1E40AF] hover:bg-blue-50 transition-all group"
    >
      <div className="flex items-center gap-3">
        <span className="w-8 h-8 rounded-full bg-[#1E40AF] text-white text-sm font-bold flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform">
          {step}
        </span>
        <div>
          <p className="font-semibold text-slate-800 text-sm">{label}</p>
          <p className="text-xs text-slate-500">{desc}</p>
        </div>
        <span className="ml-auto text-slate-400 group-hover:text-[#1E40AF]">→</span>
      </div>
    </button>
  )
}

function SubViewButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left px-4 py-2.5 rounded-lg border border-slate-200 hover:border-[#1E40AF] hover:bg-blue-50 transition-all text-sm text-slate-700"
    >
      {label} →
    </button>
  )
}
