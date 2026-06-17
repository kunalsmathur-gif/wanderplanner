'use client'

import { ThreeColumnLayout } from '@/components/layout/ThreeColumnLayout'
import { ConversationalWizard } from '@/components/wizard/ConversationalWizard'
import { FloatingAnyaButton } from '@/components/common/FloatingAnyaButton'
import { useAppStore } from '@/store/appStore'

export default function Home() {
  const wizardOpen = useAppStore((state) => state.wizardOpen)

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <div
        className={wizardOpen
          ? 'pointer-events-none flex-1 select-none overflow-hidden blur-sm'
          : 'flex-1 overflow-hidden'}
      >
        <ThreeColumnLayout />
      </div>

      {/* Floating Anya button - always visible on itinerary page */}
      <FloatingAnyaButton />

      {wizardOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <ConversationalWizard />
        </div>
      )}
    </div>
  )
}
