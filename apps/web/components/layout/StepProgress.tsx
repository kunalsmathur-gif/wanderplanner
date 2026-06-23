'use client'

import { Check } from 'lucide-react'
import type { AppStep } from '@/store/appStore'

const STEPS = [
  { label: 'Plan Your Trip' },
  { label: 'Itinerary Overview' },
  { label: 'Detailed Itinerary' },
]

export function StepProgress({ currentStep }: { currentStep: AppStep }) {
  return (
    <nav
      aria-label="Wizard progress"
      className="flex shrink-0 items-center border-b border-[var(--_border)] bg-[var(--_card)] px-6 py-2.5"
    >
      <ol className="flex items-center">
        {STEPS.map((s, i) => {
          const stepNum = (i + 1) as AppStep
          const isActive = stepNum === currentStep
          const isDone = stepNum < currentStep

          return (
            <li key={s.label} className="flex items-center" data-step={stepNum}>
              <div className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className={[
                    'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold',
                    isActive
                      ? 'bg-[var(--_primary)] text-[var(--_on-primary)]'
                      : isDone
                        ? 'bg-[var(--_success)] text-white'
                        : 'bg-[var(--_muted)] text-[var(--_muted-fg)]',
                  ].join(' ')}
                >
                  {isDone ? <Check size={12} strokeWidth={3} /> : stepNum}
                </span>
                <span
                  aria-current={isActive ? 'step' : undefined}
                  className={[
                    'text-sm',
                    isActive
                      ? 'font-semibold text-[var(--_primary)]'
                      : isDone
                        ? 'text-[var(--_success)]'
                        : 'text-[var(--_muted-fg)]',
                  ].join(' ')}
                >
                  {s.label}
                  <span className="sr-only">
                    {isDone ? ' (completed)' : isActive ? ' (current)' : ' (upcoming)'}
                  </span>
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div
                  aria-hidden="true"
                  className={[
                    'mx-3 h-px w-10',
                    isDone ? 'bg-[var(--_success)]' : 'bg-[var(--_border)]',
                  ].join(' ')}
                />
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
