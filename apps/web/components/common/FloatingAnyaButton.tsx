'use client'

import { useAppStore } from '@/store/appStore'
import { useChatStore } from '@/store/chatStore'
import { ListeningOrb } from '@/components/voice/ListeningOrb'

export function FloatingAnyaButton() {
  const openWizard = useAppStore((state) => state.openWizard)
  const wizardOpen = useAppStore((state) => state.wizardOpen)
  const openChat = useChatStore((state) => state.open)
  const chatOpen = useChatStore((state) => state.isOpen)

  // When itinerary exists the button opens the persistent chat; otherwise opens wizard
  const hasItinerary = typeof window !== 'undefined'
    // We check via the DOM rather than re-importing itineraryStore to avoid circular deps
    // This component is only rendered when hasItinerary=true (see page.tsx)
    ? true
    : false

  if (wizardOpen || chatOpen) return null

  function handleClick() {
    // page.tsx only renders this component when hasItinerary is true
    openChat()
  }

  return (
    // ⚠️ This is the only trigger for the *persistent chat* (`useChatStore` →
    // `ChatPanel`). "Edit Trip" is not a substitute: it calls `openWizard()`,
    // a different Anya surface that takes over the screen, blurs the dashboard
    // and fires the 'back' feedback prompt, because it exists to change trip
    // config rather than ask about the plan in place.
    //
    // Mobile offset clears the frozen tab bar (~51px + the home-indicator
    // inset) rather than the fixed `bottom-24` used before v10.58 — the bar's
    // height is what this has to sit above, so it is expressed as that plus
    // the safe-area rather than a magic number that drifts when the bar does.
    <div className="fixed bottom-[calc(3.5rem+env(safe-area-inset-bottom))] right-4 z-40 lg:bottom-6 lg:right-6">
      <button
        onClick={handleClick}
        // No text label under the orb: it added height for no affordance and,
        // being wider than the orb itself, overlapped whatever sat beside it.
        // The name lives in the hover tooltip and the aria-label, so nothing
        // is lost to assistive tech.
        className="group flex items-center justify-center transition-transform hover:scale-105"
        aria-label="Ask Anya about this plan"
        type="button"
      >
        <div className="relative">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-10 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-[var(--_card-elevated)] px-3 py-1.5 text-xs font-medium text-[var(--_fg)] shadow-lg opacity-0 transition-opacity group-hover:opacity-100"
            style={{ border: '1px solid var(--_border)' }}
          >
            {/* Names the job, not the persona. "Chat with Anya" said nothing
                about how this differs from "Edit Trip", which also reaches
                Anya — via the guided wizard that replaces the dashboard. */}
            Ask Anya about this plan
          </div>
          {/* 44px on a phone (a full touch target at its smallest), the
              original 72px from lg up. The footprint was the complaint: at
              72px plus the label it stood ~98px tall over a phone-width
              column. */}
          <ListeningOrb
            isActive={false}
            isRecording={false}
            svgClassName="h-11 w-11 lg:h-[72px] lg:w-[72px]"
          />
        </div>
      </button>
    </div>
  )
}
