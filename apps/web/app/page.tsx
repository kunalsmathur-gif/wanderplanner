'use client'

import { useAppStore } from '@/store/appStore'
import { WizardForm } from '@/components/wizard/WizardForm'
import { ItineraryOverview } from '@/components/itinerary/ItineraryOverview'
import { ThreeColumnLayout } from '@/components/layout/ThreeColumnLayout'
import { TopNav } from '@/components/layout/TopNav'
import { StepProgress } from '@/components/layout/StepProgress'

export default function Home() {
  const step = useAppStore((s) => s.step)

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <TopNav />
      <StepProgress currentStep={step} />
      <main id="main-content" role="main" className="flex-1 overflow-hidden">
        {step === 1 && <WizardForm />}
        {step === 2 && <ItineraryOverview />}
        {step === 3 && <ThreeColumnLayout />}
      </main>
    </div>
  )
}
