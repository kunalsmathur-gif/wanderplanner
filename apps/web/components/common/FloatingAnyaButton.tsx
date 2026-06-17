'use client'

import { useAppStore } from '@/store/appStore'
import { ListeningOrb } from '@/components/voice/ListeningOrb'

export function FloatingAnyaButton() {
  const openWizard = useAppStore((state) => state.openWizard)
  const wizardOpen = useAppStore((state) => state.wizardOpen)

  // Don't show when wizard is already open
  if (wizardOpen) return null

  return (
    <div className="fixed bottom-6 right-6 z-40 flex flex-col items-center gap-2">
      {/* Tooltip */}
      <div className="rounded-lg bg-[#1A3A52] px-4 py-2 text-sm text-white shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
        Talk to Anya
      </div>
      
      {/* Orb Button */}
      <button
        onClick={openWizard}
        className="group relative flex flex-col items-center transition-transform hover:scale-105"
        aria-label="Open Anya chat"
        type="button"
      >
        <ListeningOrb 
          isActive={false}
          isRecording={false}
        />
        
        {/* Label */}
        <span className="mt-2 font-display text-sm font-bold text-[#1A3A52]">
          Anya
        </span>
      </button>
    </div>
  )
}
