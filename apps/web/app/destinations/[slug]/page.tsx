import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft, Calendar, Wallet, Sparkles } from 'lucide-react'
import { WanderplannerLogo } from '@/components/common/WanderplannerLogo'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { DestinationHeroImage } from '@/components/common/DestinationHeroImage'
import { PlanTripCta } from '@/components/common/PlanTripCta'
import { destinations, destinationBySlug } from '@/lib/destinationsData'

const SITE_URL = 'https://wanderplanner.org'

export function generateStaticParams() {
  return destinations.map((d) => ({ slug: d.slug }))
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>
}): Promise<Metadata> {
  const { slug } = await params
  const dest = destinationBySlug.get(slug)
  if (!dest) return { title: 'Destination not found' }

  const url = `${SITE_URL}/destinations/${dest.slug}`
  return {
    title: dest.metaTitle,
    description: dest.metaDescription,
    keywords: dest.keywords,
    alternates: { canonical: url },
    openGraph: {
      type: 'article',
      url,
      siteName: 'Wanderplanner',
      title: dest.metaTitle,
      description: dest.metaDescription,
    },
    twitter: {
      card: 'summary_large_image',
      title: dest.metaTitle,
      description: dest.metaDescription,
    },
  }
}

export default async function DestinationPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  const dest = destinationBySlug.get(slug)
  if (!dest) notFound()

  const url = `${SITE_URL}/destinations/${dest.slug}`

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'TouristTrip',
    name: `${dest.recommendedDays}-Day ${dest.label} Itinerary`,
    description: dest.metaDescription,
    url,
    provider: { '@type': 'Organization', name: 'Wanderplanner', url: SITE_URL },
    itinerary: dest.sampleItinerary.map((day, i) => ({
      '@type': 'Trip',
      name: `Day ${i + 1}: ${day.title}`,
    })),
  }

  const faqJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: dest.faqs.map((f) => ({
      '@type': 'Question',
      name: f.q,
      acceptedAnswer: { '@type': 'Answer', text: f.a },
    })),
  }

  return (
    <div className="min-h-screen bg-[var(--_bg)]">
      {/* biome-ignore lint/security/noDangerouslySetInnerHtml: structured data JSON-LD */}
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      {/* biome-ignore lint/security/noDangerouslySetInnerHtml: structured data JSON-LD */}
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd) }} />

      <header className="sticky top-0 z-10 border-b border-[var(--_border)] bg-[var(--_bg)]/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3 sm:px-6">
          <Link href="/">
            <WanderplannerLogo size="sm" wordmark />
          </Link>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Link
              href="/destinations"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--_primary)] hover:underline"
            >
              <ArrowLeft size={16} />
              All destinations
            </Link>
          </div>
        </div>
      </header>

      <DestinationHeroImage
        heroImage={dest.heroImage}
        alt={`${dest.label} — ${dest.tagline}`}
      />

      <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <p className="text-xs font-bold uppercase tracking-widest text-[var(--_primary)]">
          {dest.emoji} Destination guide
        </p>
        <h1 className="font-display mt-2 text-3xl font-black leading-tight text-[var(--_fg)] sm:text-4xl">
          {dest.label} Trip Planner — {dest.recommendedDays}-Day Itinerary
        </h1>
        <p className="mt-3 text-base leading-relaxed text-[var(--_muted-fg)]">{dest.tagline}</p>

        {/* Quick facts strip */}
        <div className="mt-6 flex flex-wrap gap-3">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--_border)] bg-[var(--_card)] px-3 py-1.5 text-xs font-semibold text-[var(--_fg)]">
            <Calendar size={13} /> {dest.recommendedDays} days recommended
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--_border)] bg-[var(--_card)] px-3 py-1.5 text-xs font-semibold text-[var(--_fg)]">
            <Wallet size={13} /> {dest.budgetINR} per person
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--_border)] bg-[var(--_card)] px-3 py-1.5 text-xs font-semibold text-[var(--_fg)]">
            <Sparkles size={13} /> AI-personalised
          </span>
        </div>

        <div className="mt-6">
          <PlanTripCta slug={dest.slug} label={dest.label} />
        </div>

        {/* Overview */}
        <section className="mt-10">
          <h2 className="font-display text-xl font-bold text-[var(--_fg)]">Overview</h2>
          {dest.overview.map((p, i) => (
            <p key={i} className="mt-3 text-sm leading-relaxed text-[var(--_muted-fg)]">
              {p}
            </p>
          ))}
        </section>

        {/* Highlights */}
        <section className="mt-8">
          <h2 className="font-display text-xl font-bold text-[var(--_fg)]">Highlights</h2>
          <ul className="mt-3 space-y-1.5">
            {dest.highlights.map((h) => (
              <li key={h} className="flex gap-2 text-sm text-[var(--_muted-fg)]">
                <span aria-hidden="true">📍</span> {h}
              </li>
            ))}
          </ul>
        </section>

        {/* Best time to visit */}
        <section className="mt-8">
          <h2 className="font-display text-xl font-bold text-[var(--_fg)]">Best time to visit</h2>
          <p className="mt-3 text-sm leading-relaxed text-[var(--_muted-fg)]">{dest.bestTimeToVisit}</p>
        </section>

        {/* Budget breakdown */}
        <section className="mt-8">
          <h2 className="font-display text-xl font-bold text-[var(--_fg)]">
            Budget breakdown ({dest.recommendedDays} days, per person)
          </h2>
          <dl className="mt-3 divide-y divide-[var(--_border)] rounded-xl border border-[var(--_border)] bg-[var(--_card)]">
            {dest.budgetBreakdown.map((b) => (
              <div key={b.category} className="flex items-center justify-between px-4 py-2.5 text-sm">
                <dt className="text-[var(--_muted-fg)]">{b.category}</dt>
                <dd className="font-semibold text-[var(--_fg)]">{b.amount}</dd>
              </div>
            ))}
          </dl>
        </section>

        {/* Sample itinerary */}
        <section className="mt-8">
          <h2 className="font-display text-xl font-bold text-[var(--_fg)]">
            Sample {dest.recommendedDays}-day itinerary
          </h2>
          <div className="mt-4 space-y-4">
            {dest.sampleItinerary.map((day, i) => (
              <div key={i} className="rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-4">
                <h3 className="font-display text-sm font-bold text-[var(--_fg)]">
                  Day {i + 1}: {day.title}
                </h3>
                <ul className="mt-2 space-y-1">
                  {day.items.map((item) => (
                    <li key={item} className="text-sm text-[var(--_muted-fg)]">
                      • {item}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs text-[var(--_muted-fg)]">
            This is a starting point — Wanderplanner's AI concierge Anya personalises pacing, budget, and activities
            to your actual dates, group, and interests.
          </p>
        </section>

        {/* FAQ */}
        <section className="mt-8">
          <h2 className="font-display text-xl font-bold text-[var(--_fg)]">Frequently asked questions</h2>
          <dl className="mt-3 space-y-5">
            {dest.faqs.map((f) => (
              <div key={f.q}>
                <dt className="text-sm font-bold text-[var(--_fg)]">{f.q}</dt>
                <dd className="mt-1 text-sm leading-relaxed text-[var(--_muted-fg)]">{f.a}</dd>
              </div>
            ))}
          </dl>
        </section>

        {/* Bottom CTA */}
        <div className="mt-12 rounded-2xl bg-[var(--_primary)] p-8 text-center">
          <p className="font-display text-xl font-bold text-white">
            Ready to plan your {dest.label} trip?
          </p>
          <p className="mt-2 text-sm text-white/80">
            Free AI itinerary, personalised to your dates, budget, and group.
          </p>
          <Link
            href={`/?dest=${dest.slug}`}
            className="mt-4 inline-block rounded-xl bg-white px-6 py-3 text-sm font-bold text-[var(--_primary)] transition-opacity hover:opacity-90"
          >
            Start planning for free
          </Link>
        </div>
      </main>
    </div>
  )
}
