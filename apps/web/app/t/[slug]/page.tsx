'use client'

import { useEffect, useState } from 'react'
import { WanderplanLogo } from '@/components/common/WanderplanLogo'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import type { ItineraryDay, ExpenseBreakdown } from '@/types'

interface SharedData {
  itinerary: { days: ItineraryDay[]; alignment_score: number; expense_breakdown?: ExpenseBreakdown }
  trip_config: Record<string, unknown>
  labels: Record<string, string>
  destination_label: string
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export default function SharedTripPage({ params }: { params: { slug: string } }) {
  const [data, setData] = useState<SharedData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch(`${BASE_URL}/api/share/${params.slug}`)
      .then((r) => { if (!r.ok) throw new Error('not found'); return r.json() })
      .then((d) => setData(d as SharedData))
      .catch(() => setError("This trip link has expired or doesn't exist."))
  }, [params.slug])

  return (
    <div className="min-h-screen bg-[var(--_bg)] text-[var(--_fg)]">
      {/* Minimal nav */}
      <header className="sticky top-0 z-10 border-b border-[var(--_border)] bg-[var(--_bg)]/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-3">
          <WanderplanLogo size="md" wordmark />
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <a
              href="/"
              className="btn btn-primary rounded-xl px-4 py-2 text-sm"
            >
              Plan my own trip →
            </a>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-10">
        {error && (
          <div className="rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-10 text-center">
            <p className="text-2xl">😔</p>
            <p className="mt-3 font-semibold text-[var(--_fg)]">{error}</p>
            <a href="/" className="mt-4 inline-block text-sm text-[var(--_primary)] hover:underline">
              ← Plan a new trip
            </a>
          </div>
        )}

        {!data && !error && (
          <div className="flex items-center justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--_primary)] border-t-transparent" />
          </div>
        )}

        {data && (
          <>
            <div className="mb-8">
              <p className="text-xs font-bold uppercase tracking-widest text-[var(--_primary)]">
                Shared Trip
              </p>
              <h1 className="font-display mt-1 text-3xl font-black text-[var(--_fg)]">
                {data.destination_label || 'Your Adventure'}
              </h1>
              {data.labels?.duration && (
                <p className="mt-1 text-[var(--_muted-fg)]">{data.labels.duration}</p>
              )}
              <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-amber-300/60 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700 dark:border-amber-700/40 dark:bg-amber-950/30 dark:text-amber-400">
                👁 View-only — plan your own trip to personalise it
              </div>
            </div>

            {/* Day-by-day itinerary */}
            <div className="space-y-8">
              {data.itinerary.days.map((day, i) => (
                <section key={i} className="rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-6">
                  <h2 className="font-display mb-4 text-lg font-bold text-[var(--_fg)]">
                    Day {i + 1}{day.date ? ` · ${day.date}` : ''}
                  </h2>
                  <div className="space-y-3">
                    {day.items?.map((item, j) => (
                      <div key={j} className="flex gap-3">
                        <span className="mt-0.5 text-lg">📍</span>
                        <div>
                          <p className="font-semibold text-[var(--_fg)]">{item.title}</p>
                          {item.description && (
                            <p className="mt-0.5 text-sm text-[var(--_muted-fg)]">{item.description}</p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>

            {/* CTA footer */}
            <div className="mt-10 rounded-2xl bg-[var(--_primary)] p-8 text-center">
              <p className="font-display text-xl font-bold text-white">
                Inspired? Plan your own version →
              </p>
              <p className="mt-2 text-sm text-white/80">
                Personalise the destination, dates, budget and group — free, no sign-up.
              </p>
              <a
                href="/"
                className="mt-4 inline-block rounded-xl bg-white px-6 py-3 text-sm font-bold text-[var(--_primary)] transition-opacity hover:opacity-90"
              >
                Start planning for free
              </a>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
