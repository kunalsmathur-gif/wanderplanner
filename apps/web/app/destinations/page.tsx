import type { Metadata } from 'next'
import Link from 'next/link'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { WanderplannerLogo } from '@/components/common/WanderplannerLogo'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { destinations } from '@/lib/destinationsData'

const SITE_URL = 'https://wanderplanner.org'

export const metadata: Metadata = {
  title: 'Destination Guides — AI Trip Planner',
  description:
    'Browse AI-personalised trip guides for Bali, Rajasthan, Dubai, Europe, and more — day-by-day itineraries, budgets, and best time to visit.',
  alternates: { canonical: `${SITE_URL}/destinations` },
}

export default function DestinationsIndexPage() {
  return (
    <div className="min-h-screen bg-[var(--_bg)]">
      <header className="sticky top-0 z-10 border-b border-[var(--_border)] bg-[var(--_bg)]/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3 sm:px-6">
          <Link href="/">
            <WanderplannerLogo size="sm" wordmark />
          </Link>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Link href="/" className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--_primary)] hover:underline">
              <ArrowLeft size={16} />
              Back to home
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
        <p className="text-xs font-bold uppercase tracking-widest text-[var(--_primary)]">Destination guides</p>
        <h1 className="font-display mt-2 text-3xl font-black text-[var(--_fg)] sm:text-4xl">
          Where do you want to go?
        </h1>
        <p className="mt-3 max-w-xl text-base text-[var(--_muted-fg)]">
          Day-by-day sample itineraries, budgets, and best-time-to-visit guides — then let Anya personalise one to
          your actual dates and group.
        </p>

        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {destinations.map((d) => (
            <Link
              key={d.slug}
              href={`/destinations/${d.slug}`}
              className="group rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-6 transition-all hover:-translate-y-0.5 hover:border-[var(--_primary)] hover:shadow-lg"
            >
              <span className="text-2xl">{d.emoji}</span>
              <h2 className="font-display mt-3 text-lg font-bold text-[var(--_fg)]">{d.label}</h2>
              <p className="mt-1 text-sm text-[var(--_muted-fg)]">{d.tagline}</p>
              <div className="mt-3 flex items-center justify-between text-xs font-semibold text-[var(--_muted-fg)]">
                <span>{d.recommendedDays} days · {d.budgetINR}</span>
                <span className="inline-flex items-center gap-1 text-[var(--_primary)] opacity-70 group-hover:opacity-100">
                  Read guide <ArrowRight size={12} />
                </span>
              </div>
            </Link>
          ))}
        </div>
      </main>
    </div>
  )
}
