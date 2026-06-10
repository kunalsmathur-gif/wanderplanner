'use client'

import type { AppStep } from '@/store/appStore'

const STEPS = [
  { label: 'Plan Your Trip' },
  { label: 'Itinerary Overview' },
  { label: 'Detailed Itinerary' },
]

export function StepProgress({ currentStep }: { currentStep: AppStep }) {
  return (
    <div className="flex items-center gap-0 bg-white border-b border-slate-200 px-6 py-2 shrink-0">
      {STEPS.map((s, i) => {
        const stepNum = (i + 1) as AppStep
        const isActive = stepNum === currentStep
        const isDone = stepNum < currentStep

        return (
          <div key={s.label} className="flex items-center">
            <div className="flex items-center gap-2">
              <span
                className={[
                  'w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold shrink-0',
                  isActive ? 'bg-[#1E40AF] text-white' : '',
                  isDone ? 'bg-[#047857] text-white' : '',
                  !isActive && !isDone ? 'bg-slate-200 text-slate-500' : '',
                ].join(' ')}
              >
                {isDone ? '✓' : stepNum}
              </span>
              <span
                className={[
                  'text-sm',
                  isActive ? 'text-[#1E40AF] font-medium' : '',
                  isDone ? 'text-[#047857]' : '',
                  !isActive && !isDone ? 'text-slate-400' : '',
                ].join(' ')}
              >
                {s.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div
                className={[
                  'h-px w-10 mx-3',
                  isDone ? 'bg-[#047857]' : 'bg-slate-200',
                ].join(' ')}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
