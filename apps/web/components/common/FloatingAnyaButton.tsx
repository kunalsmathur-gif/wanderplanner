'use client'

import { useAppStore } from '@/store/appStore'
import { ListeningOrb } from '@/components/voice/ListeningOrb'

export function FloatingAnyaButton() {
  const openWizard = useAppStore((state) => state.openWizard)
  const wizardOpen = useAppStore((state) => state.wizardOpen)

  if (wizardOpen) return null

  return (
    <div className="fixed bottom-6 right-6 z-40">
      <button
        onClick={openWizard}
        className="group flex flex-col items-center gap-1.5 transition-transform hover:scale-105"
        aria-label="Open Anya — Wanderplan concierge"
        type="button"
      >
        <div className="relative">
          {/* Tooltip */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-10 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-[var(--_card-elevated)] px-3 py-1.5 text-xs font-medium text-[var(--_fg)] shadow-lg opacity-0 transition-opacity group-hover:opacity-100"
            style={{ border: '1px solid var(--_border)' }}
          >
            Talk to your concierge
          </div>
          <ListeningOrb isActive={false} isRecording={false} />
        </div>
        <span className="font-display text-sm font-bold text-[var(--_fg)]">
          Anya
        </span>
      </button>
    </div>
  )
}
