'use client'

import { useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'

export function MobileWarningBanner() {
  const [dismissed, setDismissed] = useState(false)
  if (dismissed) return null

  return (
    <div
      role="alert"
      className="flex items-start gap-3 border-b border-[var(--_border)] bg-[var(--_card)] px-4 py-3 text-sm text-[var(--_fg)] lg:hidden"
    >
      <AlertTriangle size={16} className="mt-0.5 shrink-0 text-[var(--_accent)]" aria-hidden="true" />
      <p className="flex-1">
        WanderPlan is designed for desktop. For the best experience, open it on a laptop or desktop screen (1200px+).
      </p>
      <button
        onClick={() => setDismissed(true)}
        aria-label="Dismiss warning"
        className="shrink-0 rounded p-0.5 text-[var(--_muted-fg)] transition-colors hover:text-[var(--_fg)]"
      >
        <X size={16} />
      </button>
    </div>
  )
}
