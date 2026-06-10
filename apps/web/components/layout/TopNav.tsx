'use client'

import { useAppStore } from '@/store/appStore'
import { useItineraryStore } from '@/store/itineraryStore'

export function TopNav() {
  const step = useAppStore((s) => s.step)
  const days = useItineraryStore((s) => s.days)

  return (
    <header className="h-12 bg-[#1E40AF] text-white flex items-center px-6 gap-4 shrink-0">
      <span className="font-semibold text-base tracking-wide">[W] WanderPlan</span>
      {step > 1 && days.length > 0 && (
        <span className="text-sm text-blue-200 truncate hidden lg:block">
          {days[0]?.date} – {days[days.length - 1]?.date}
        </span>
      )}
      <div className="ml-auto text-sm text-blue-200">
        {step > 1 && `${days.length} day${days.length !== 1 ? 's' : ''} planned`}
      </div>
    </header>
  )
}
