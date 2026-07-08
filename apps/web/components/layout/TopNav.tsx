'use client'

import { useAppStore } from '@/store/appStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { WanderplannerLogo } from '@/components/common/WanderplannerLogo'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { UserMenu } from '@/components/common/UserMenu'

export function TopNav() {
  const step = useAppStore((s) => s.step)
  const days = useItineraryStore((s) => s.days)

  return (
    <header
      role="banner"
      className="nav-header flex h-14 shrink-0 items-center gap-4 px-5"
    >
      <WanderplannerLogo size="sm" inverted />

      {step > 1 && days.length > 0 && (
        <span
          className="hidden truncate text-sm text-white/70 lg:block"
          aria-label="Trip date range"
        >
          {days[0]?.date} – {days[days.length - 1]?.date}
        </span>
      )}

      <div className="ml-auto flex items-center gap-3">
        {step > 1 && days.length > 0 && (
          <span className="text-sm text-white/70" aria-live="polite">
            {days.length} day{days.length !== 1 ? 's' : ''} planned
          </span>
        )}
        <ThemeToggle />
        <UserMenu inverted />
      </div>
    </header>
  )
}
