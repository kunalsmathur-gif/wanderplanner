'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ThreeColumnLayout } from '@/components/layout/ThreeColumnLayout'
import { LLMWizard } from '@/components/wizard/LLMWizard'
import { FloatingAnyaButton } from '@/components/common/FloatingAnyaButton'
import { ChatPanel } from '@/components/chat/ChatPanel'
import { useAppStore } from '@/store/appStore'
import { useAuthStore } from '@/store/authStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { loadLastItinerary } from '@/lib/resumeLastItinerary'

/**
 * The generated trip, at its own URL.
 *
 * Previously this rendered inside `/` off `days.length > 0`, so the address
 * bar never changed between the landing page and a generated itinerary —
 * back/forward did nothing useful, the trip could not be linked to, and
 * logging out could not navigate away from it (`router.push('/')` was a no-op
 * on the page you were already on, which is why logout appeared to do
 * nothing).
 */
export default function ItineraryPage() {
  const router = useRouter()
  const wizardOpen = useAppStore((state) => state.wizardOpen)
  const days = useItineraryStore((state) => state.days)
  const hasItinerary = days.length > 0
  const authStatus = useAuthStore((state) => state.status)

  // 🔴 Hydration state is read in an effect, never during render, and through
  // optional chaining. zustand's `persist` middleware **returns early without
  // attaching the `.persist` API at all** when its storage is unavailable —
  // which is exactly the case while Next prerenders this page at build time,
  // since `sessionStorage` does not exist on the server. Touching
  // `useItineraryStore.persist.hasHydrated()` in the render body therefore
  // threw `Cannot read properties of undefined` and failed the production
  // build. `next dev` never caught it because it does not prerender.
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    const store = useItineraryStore.persist
    // No persistence available (server, or a browser refusing storage) means
    // there is nothing to wait for — treat it as hydrated and let the empty
    // check below do its job.
    if (!store) {
      setHydrated(true)
      return
    }
    if (store.hasHydrated()) {
      setHydrated(true)
      return
    }
    return store.onFinishHydration(() => setHydrated(true))
  }, [])

  useEffect(() => {
    // Wait for the sessionStorage rehydration to finish before deciding the
    // page is empty — on the first client render `days` is always [], so
    // redirecting eagerly would bounce every refresh back to the landing page,
    // which is the exact failure this route was added to avoid.
    if (!hydrated || hasItinerary) return

    // Also wait for auth to resolve. `sessionStorage` can be dropped by
    // events entirely outside our control — an external link (e.g. a
    // YouTube video thumbnail) navigating the same tab, a mobile browser
    // reclaiming memory while backgrounded, the 15-minute access token
    // expiring mid-visit and needing a silent refresh — none of which mean
    // the trip is actually gone server-side. Bouncing to the landing page
    // while `authStatus` is still `idle`/`loading` treated every one of
    // those as a hard "no trip", permanently losing a signed-in user's
    // itinerary and (going back to it) dropping them one page short of
    // where they started, on `/` instead of `/account`.
    if (authStatus === 'idle' || authStatus === 'loading') return

    let cancelled = false
    if (authStatus === 'authenticated') {
      // Signed in: the trip is still saved server-side, so re-fetch it
      // instead of giving up. Only redirect if that also comes back empty.
      loadLastItinerary().then((resumed) => {
        if (cancelled) return
        if (!resumed) router.replace('/account')
      })
    } else {
      router.replace('/')
    }
    return () => {
      cancelled = true
    }
  }, [hydrated, hasItinerary, authStatus, router])

  if (!hasItinerary) {
    return (
      <div className="flex h-dvh items-center justify-center" aria-live="polite">
        <span className="text-sm text-[var(--_muted-fg)]">
          {hydrated ? 'No itinerary yet — taking you back…' : 'Loading your itinerary…'}
        </span>
      </div>
    )
  }

  // 🔴 `h-dvh`, not `h-screen`. On mobile `100vh` is the *large* viewport — it
  // includes the strip behind the collapsing URL bar — so a 100vh column is
  // taller than what you can actually see, and its last child (the bottom tab
  // bar) started below the fold. That is why the tabs only showed up once you
  // scrolled all the way down. `100dvh` tracks the visible viewport, so the
  // tab bar's `bottom-0` lands on the bottom of the screen.
  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <div
        className={wizardOpen
          ? 'pointer-events-none flex-1 select-none overflow-hidden opacity-40 blur-sm transition-all'
          : 'flex-1 overflow-hidden'}
        aria-hidden={wizardOpen}
      >
        <main id="main-content" aria-label="Wanderplanner itinerary dashboard" className="h-full">
          <ThreeColumnLayout />
        </main>
      </div>

      <FloatingAnyaButton />
      <ChatPanel />

      {wizardOpen && <LLMWizard />}
    </div>
  )
}
