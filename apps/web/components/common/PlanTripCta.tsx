'use client'

import Link from 'next/link'
import { ArrowRight } from 'lucide-react'

/**
 * CTA on destination landing pages. Plain link (not a direct wizard-open
 * call) because these are server-rendered pages with no access to the
 * zustand store — `/?dest=<slug>` is read by LandingHero on mount to
 * auto-open the wizard pre-filled with this destination.
 */
export function PlanTripCta({ slug, label }: { slug: string; label: string }) {
  return (
    <Link
      href={`/?dest=${slug}`}
      className="btn btn-accent inline-flex items-center gap-2 rounded-2xl px-6 py-3.5 text-sm font-bold shadow-lg sm:px-8 sm:py-4 sm:text-base"
    >
      Customize my {label} itinerary <ArrowRight size={18} />
    </Link>
  )
}
