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
    // Desktop only. On a phone the orb is ~98px of permanently-floating
    // chrome over an already tight column, and it sat directly on top of
    // whatever scrolled beneath it — it was covering the "Get Quotation" CTA
    // and winning the tap.
    //
    // ⚠️ This is the only trigger for the *persistent chat* (`useChatStore` →
    // `ChatPanel`) on either breakpoint. "Edit Trip" is not a substitute: it
    // calls `openWizard()`, which is a different Anya surface — it takes over
    // the screen, blurs the dashboard and fires the 'back' feedback prompt,
    // because it exists to change the trip config, not to ask questions about
    // the plan in place. So mobile gets its own trigger in the title bar
    // (`ThreeColumnLayout.tsx::AnyaTitleBarButton`); keep the two in step.
    <div className="fixed bottom-6 right-6 z-40 hidden lg:block">
      <button
        onClick={handleClick}
        className="group flex flex-col items-center gap-1.5 transition-transform hover:scale-105"
        aria-label="Open Anya — Wanderplanner concierge"
        type="button"
      >
        <div className="relative">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-10 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-[var(--_card-elevated)] px-3 py-1.5 text-xs font-medium text-[var(--_fg)] shadow-lg opacity-0 transition-opacity group-hover:opacity-100"
            style={{ border: '1px solid var(--_border)' }}
          >
            Chat with Anya
          </div>
          <ListeningOrb isActive={false} isRecording={false} />
        </div>
        <span className="font-display text-sm font-bold text-[var(--_fg)]">Anya</span>
      </button>
    </div>
  )
}
