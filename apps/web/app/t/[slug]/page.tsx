import type { Metadata } from 'next'
import { WanderplannerLogo } from '@/components/common/WanderplannerLogo'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { formatDayDate } from '@/lib/format'
import { getSharedTrip } from '@/lib/sharedTrip'

const SITE_URL = 'https://wanderplanner.app'

const TAG_BADGE: Record<string, { emoji: string; className: string }> = {
  hidden_gem: {
    emoji: '💎',
    className:
      'rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium text-violet-700 dark:bg-violet-900 dark:text-violet-300',
  },
  pinned: {
    emoji: '📌',
    className:
      'rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 dark:bg-amber-900 dark:text-amber-300',
  },
  instaworthy: {
    emoji: '📸',
    className: 'rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-700 dark:text-slate-400',
  },
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>
}): Promise<Metadata> {
  const { slug } = await params
  const data = await getSharedTrip(slug)

  if (!data) {
    return { title: 'Shared trip', robots: { index: false, follow: false } }
  }

  const destination = data.destination_label || 'a personalised trip'
  const title = `${destination} itinerary`
  const description = data.labels?.duration
    ? `A ${data.labels.duration} AI-planned itinerary for ${destination} — day-by-day activities, budget, and local tips. Made with Wanderplanner.`
    : `An AI-planned itinerary for ${destination} — day-by-day activities, budget, and local tips. Made with Wanderplanner.`
  const url = `${SITE_URL}/t/${slug}`

  return {
    title,
    description,
    robots: { index: false, follow: false }, // shared trips aren't meant to rank, just unfurl nicely
    alternates: { canonical: url },
    openGraph: {
      type: 'article',
      url,
      siteName: 'Wanderplanner',
      title,
      description,
      images: [{ url: `/t/${slug}/opengraph-image`, width: 1200, height: 630, alt: title }],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [`/t/${slug}/opengraph-image`],
    },
  }
}

export default async function SharedTripPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const data = await getSharedTrip(slug)

  return (
    <div className="min-h-screen bg-[var(--_bg)] text-[var(--_fg)]">
      {/* Minimal nav */}
      <header className="sticky top-0 z-10 border-b border-[var(--_border)] bg-[var(--_bg)]/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-3">
          <WanderplannerLogo size="md" wordmark />
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <a href="/" className="btn btn-primary rounded-xl px-4 py-2 text-sm">
              Plan my own trip →
            </a>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-10">
        {!data && (
          <div className="rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-10 text-center">
            <p className="text-2xl">😔</p>
            <p className="mt-3 font-semibold text-[var(--_fg)]">This trip link has expired or doesn&apos;t exist.</p>
            <a href="/" className="mt-4 inline-block text-sm text-[var(--_primary)] hover:underline">
              ← Plan a new trip
            </a>
          </div>
        )}

        {data && (
          <>
            <div className="mb-8">
              <p className="text-xs font-bold uppercase tracking-widest text-[var(--_primary)]">Shared Trip</p>
              <h1 className="font-display mt-1 text-3xl font-black text-[var(--_fg)]">
                {data.destination_label || 'Your Adventure'}
              </h1>
              {data.labels?.duration && <p className="mt-1 text-[var(--_muted-fg)]">{data.labels.duration}</p>}
              <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-amber-300/60 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700 dark:border-amber-700/40 dark:bg-amber-950/30 dark:text-amber-400">
                👁 View-only — plan your own trip to personalise it
              </div>
            </div>

            {/* Day-by-day itinerary */}
            <div className="space-y-8">
              {data.itinerary.days.map((day, i) => (
                <section key={i} className="rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-6">
                  <h2 className="font-display mb-4 text-lg font-bold text-[var(--_fg)]">
                    Day {i + 1}
                    {day.date ? ` · ${formatDayDate(day.date)}` : ''}
                  </h2>
                  <div className="space-y-3">
                    {day.items?.map((item, j) => {
                      const extraTags = item.tags?.filter((tag) => tag in TAG_BADGE) ?? []
                      return (
                        <div key={j} className="flex gap-3">
                          <span className="mt-0.5 text-lg">📍</span>
                          <div>
                            <p className="font-semibold text-[var(--_fg)]">{item.title}</p>
                            {item.description && (
                              <p className="mt-0.5 text-sm text-[var(--_muted-fg)]">{item.description}</p>
                            )}
                            {extraTags.length > 0 && (
                              <div className="mt-1.5 flex flex-wrap gap-1">
                                {extraTags.map((tag) => (
                                  <span key={tag} className={TAG_BADGE[tag].className}>
                                    {TAG_BADGE[tag].emoji} {tag.replace(/_/g, ' ')}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </section>
              ))}
            </div>

            {/* CTA footer */}
            <div className="mt-10 rounded-2xl bg-[var(--_primary)] p-8 text-center">
              <p className="font-display text-xl font-bold text-white">Inspired? Plan your own version →</p>
              <p className="mt-2 text-sm text-white/80">
                Personalise the destination, dates, budget and group — free with a quick sign-up.
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
