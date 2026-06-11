'use client'

import { useState } from 'react'

export function MobileWarningBanner() {
  const [dismissed, setDismissed] = useState(false)
  if (dismissed) return null

  return (
    <div
      role="alert"
      className="lg:hidden flex items-start gap-3 bg-amber-50 border-b border-amber-200 px-4 py-3 text-sm text-amber-800"
    >
      <span aria-hidden="true">⚠️</span>
      <p className="flex-1">
        WanderPlan is designed for desktop. For the best experience, open it on a laptop or desktop screen (1200px+).
      </p>
      <button
        onClick={() => setDismissed(true)}
        aria-label="Dismiss warning"
        className="text-amber-600 hover:text-amber-900 font-bold shrink-0"
      >
        ✕
      </button>
    </div>
  )
}
