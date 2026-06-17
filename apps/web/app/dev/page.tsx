'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useItineraryStore } from '@/store/itineraryStore'
import { useAppStore } from '@/store/appStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { MOCK_DAYS } from './mockData'

export default function DevPage() {
  const router = useRouter()
  const setDays = useItineraryStore((state) => state.setDays)
  const setStatus = useItineraryStore((state) => state.setStatus)
  const openWizard = useAppStore((state) => state.openWizard)
  const closeWizard = useAppStore((state) => state.closeWizard)
  const setStep3View = useAppStore((state) => state.setStep3View)
  const setDestination = useTripConfigStore((state) => state.setDestination)
  const updateConfig = useTripConfigStore((state) => state.updateConfig)
  const updateBudget = useTripConfigStore((state) => state.updateBudget)

  useEffect(() => {
    setDestination({ city: 'Tokyo', country: 'JP', lat: 35.6762, lon: 139.6503 })
    updateConfig({
      purpose: 'explore',
      personas: ['adventure_seeker', 'foodie'],
      pace: 'moderate',
    })
    updateBudget({ amount: 150000, currency: 'INR' })
    setDays(MOCK_DAYS, 87)
    setStatus('success')
  }, [setDays, setDestination, setStatus, updateBudget, updateConfig])

  function goHome(mode: 'wizard' | 'itinerary' | 'comparison') {
    if (mode === 'wizard') {
      openWizard()
      setStep3View('itinerary')
    } else if (mode === 'comparison') {
      closeWizard()
      setStep3View('comparison')
    } else {
      closeWizard()
      setStep3View('itinerary')
    }
    router.push('/')
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50">
      <div className="w-full max-w-md rounded-2xl bg-white p-10 shadow-lg">
        <div className="mb-8 text-center">
          <p className="text-2xl font-bold text-[#1E40AF]">✈ WanderPlan</p>
          <p className="mt-1 text-sm text-slate-500">Dev Preview — Tokyo 3-day itinerary pre-loaded</p>
        </div>

        <div className="space-y-3">
          <PreviewButton
            label="Open setup wizard"
            desc="Single-screen redesign with conversational overlay"
            onClick={() => goHome('wizard')}
          />
          <PreviewButton
            label="Open itinerary workspace"
            desc="Three-column itinerary view with setup dismissed"
            onClick={() => goHome('itinerary')}
          />
          <PreviewButton
            label="Open comparison panel"
            desc="Detailed layout with comparison mode active"
            onClick={() => goHome('comparison')}
          />
        </div>

        <p className="mt-6 text-center text-xs text-slate-400">
          This page is for local development only.
        </p>
      </div>
    </div>
  )
}

function PreviewButton({ label, desc, onClick }: {
  label: string
  desc: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group w-full rounded-xl border-2 border-slate-200 px-4 py-3 text-left transition-all hover:border-[#1E40AF] hover:bg-blue-50"
    >
      <div className="flex items-center gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#1E40AF] text-sm font-bold text-white transition-transform group-hover:scale-105">
          ✈
        </span>
        <div>
          <p className="text-sm font-semibold text-slate-800">{label}</p>
          <p className="text-xs text-slate-500">{desc}</p>
        </div>
        <span className="ml-auto text-slate-400 group-hover:text-[#1E40AF]">→</span>
      </div>
    </button>
  )
}
