'use client'

import { useState } from 'react'
import { Users, Wallet, MapPin, Sparkles, ArrowRight, Plane, Link2, Loader2 } from 'lucide-react'
import { useAppStore } from '@/store/appStore'
import type { WizardPreload } from '@/store/appStore'
import { WanderplannerLogo } from '@/components/common/WanderplannerLogo'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { UserMenu } from '@/components/common/UserMenu'
import { useWikiImage } from '@/hooks/useWikiImage'
import { extractTrip } from '@/lib/api'

const FEATURED_TRIPS = [
  { emoji: '🏖️', dest: 'Bali, Indonesia',    days: 7,  budget: '₹80,000',   theme: 'Beach & Temples',      gradient: 'linear-gradient(135deg,#0EA5E9 0%,#0C4A6E 100%)' },
  { emoji: '🗼', dest: 'Paris, France',       days: 5,  budget: '₹1,80,000', theme: 'Romance & Culture',    gradient: 'linear-gradient(135deg,#DB2777 0%,#831843 100%)' },
  { emoji: '🏰', dest: 'Rajasthan, India',    days: 10, budget: '₹60,000',   theme: 'Heritage & Forts',     gradient: 'linear-gradient(135deg,#D4AF37 0%,#9A3412 100%)', imageQuery: 'Amber Fort Jaipur' },
  { emoji: '🌃', dest: 'Dubai, UAE',          days: 4,  budget: '₹1,60,000', theme: 'Luxury City Break',    gradient: 'linear-gradient(135deg,#EA580C 0%,#9A3412 100%)' },
  { emoji: '⛩️', dest: 'Kyoto, Japan',        days: 7,  budget: '₹2,00,000', theme: 'Culture & Zen',        gradient: 'linear-gradient(135deg,#DC2626 0%,#7F1D1D 100%)' },
  { emoji: '🦁', dest: 'Kenya Safari',        days: 8,  budget: '₹3,50,000', theme: 'Wildlife & Nature',    gradient: 'linear-gradient(135deg,#059669 0%,#065F46 100%)' },
  { emoji: '🏔️', dest: 'Himachal Pradesh',   days: 6,  budget: '₹45,000',   theme: 'Mountains & Treks',    gradient: 'linear-gradient(135deg,#7C3AED 0%,#1E3A5F 100%)' },
  { emoji: '🌊', dest: 'Maldives',            days: 5,  budget: '₹3,00,000', theme: 'Overwater & Snorkel',  gradient: 'linear-gradient(135deg,#06B6D4 0%,#0C4A6E 100%)', imageQuery: 'Maldives tourism travel' },
  { emoji: '🌆', dest: 'Singapore',           days: 4,  budget: '₹1,00,000', theme: 'Food & Skyline',       gradient: 'linear-gradient(135deg,#0EA5E9 0%,#7C3AED 100%)' },
  { emoji: '🏝️', dest: 'Andaman Islands',    days: 6,  budget: '₹70,000',   theme: 'Beaches & Diving',     gradient: 'linear-gradient(135deg,#10B981 0%,#0C4A6E 100%)', imageQuery: 'Radhanagar Beach Andaman' },
  { emoji: '🗽', dest: 'New York, USA',       days: 7,  budget: '₹2,80,000', theme: 'Iconic City Life',     gradient: 'linear-gradient(135deg,#1E40AF 0%,#0F172A 100%)' },
  { emoji: '🌸', dest: 'Bangkok, Thailand',  days: 5,  budget: '₹55,000',   theme: 'Street Food & Temples',gradient: 'linear-gradient(135deg,#F59E0B 0%,#DC2626 100%)', imageQuery: 'Wat Pho Bangkok temple' },
]

const FEATURES = [
  {
    icon: Sparkles,
    title: 'AI-generated itineraries',
    desc: 'Day-by-day plans built around your pace, budget, and interests.',
  },
  {
    icon: Wallet,
    title: 'Budget-aware planning',
    desc: 'Every suggestion fits within your budget — no surprises.',
  },
  {
    icon: Users,
    title: 'Built for groups',
    desc: 'Handle adults, kids, varied interests — all in one trip.',
  },
  {
    icon: MapPin,
    title: 'Real travel data',
    desc: 'Reddit tips, Wikivoyage guides, and live weather baked in.',
  },
]

function InspirationCard({
  trip,
  onPlan,
}: {
  trip: typeof FEATURED_TRIPS[number]
  onPlan: (preload: WizardPreload) => void
}) {
  const city = trip.dest.split(',')[0].trim()
  const country = trip.dest.includes(',') ? trip.dest.split(',').slice(1).join(',').trim() : city
  const imgUrl = useWikiImage(city, country, trip.imageQuery)

  function handleClick() {
    onPlan({ city, country, days: trip.days, label: trip.dest })
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className="group cursor-pointer overflow-hidden rounded-2xl border border-[var(--_border)] bg-[var(--_card)] text-left shadow-sm transition-all hover:-translate-y-1 hover:border-[var(--_primary)] hover:shadow-lg"
      aria-label={`Start planning: ${trip.dest}, ${trip.days} days, ${trip.budget}`}
    >
      {/* Hero — real photo or gradient fallback */}
      <div
        className="relative h-32 w-full overflow-hidden"
        style={{ background: trip.gradient }}
      >
        {imgUrl && (
          <img
            src={imgUrl}
            alt={trip.dest}
            className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
            loading="lazy"
          />
        )}
        {/* Scrim */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/10 to-transparent" />
        {/* Theme badge bottom-left */}
        <span className="absolute bottom-3 left-3 rounded-full bg-black/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white/90 backdrop-blur-sm">
          {trip.theme}
        </span>
        {/* Emoji top-right */}
        <span className="absolute right-3 top-3 text-xl drop-shadow">{trip.emoji}</span>
      </div>

      {/* Caption */}
      <div className="px-3 pb-3 pt-2">
        <p className="text-sm font-bold leading-tight text-[var(--_fg)]">{trip.dest}</p>
        <p className="mt-0.5 text-xs text-[var(--_muted-fg)]">
          {trip.days} days · {trip.budget}
        </p>
        <span className="mt-2 inline-flex items-center gap-0.5 text-xs font-semibold text-[var(--_primary)] opacity-0 transition-opacity group-hover:opacity-100">
          Plan this <ArrowRight size={11} />
        </span>
      </div>
    </button>
  )
}

export function LandingHero() {
  const openWizard = useAppStore((s) => s.openWizard)
  const openWizardWithPreload = useAppStore((s) => s.openWizardWithPreload)

  const [startInput, setStartInput] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState('')

  async function handleStartAnywhere() {
    const val = startInput.trim()
    if (!val) { openWizard(); return }
    setExtracting(true)
    setExtractError('')
    try {
      const result = await extractTrip(val)
      if (result.destination) {
        openWizardWithPreload({
          city: result.destination,
          country: result.destination_country ?? result.destination,
          days: result.duration_days ?? 7,
          label: result.destination_country
            ? `${result.destination}, ${result.destination_country}`
            : result.destination,
        })
      } else {
        // Nothing extracted — just open wizard
        openWizard()
      }
    } catch {
      setExtractError('Could not extract trip details. Opening the wizard instead…')
      setTimeout(() => { openWizard(); setExtractError('') }, 1500)
    } finally {
      setExtracting(false)
    }
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-[var(--_bg)]">

      {/* ── Site nav ─────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 border-b border-[var(--_border)] bg-[var(--_bg)]/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-2 px-3 py-2.5 sm:px-6 sm:py-3">
          {/* Icon-only on mobile (no wordmark clutter), full logo+wordmark from sm+ */}
          <span className="sm:hidden">
            <WanderplannerLogo size="sm" wordmark={false} />
          </span>
          <span className="hidden sm:inline-flex">
            <WanderplannerLogo size="md" wordmark />
          </span>
          <nav className="flex min-w-0 items-center gap-1 sm:gap-4" aria-label="Site navigation">
            <a
              href="#inspiration"
              className="hidden text-sm font-medium text-[var(--_muted-fg)] transition-colors hover:text-[var(--_primary)] sm:block"
            >
              Inspiration
            </a>
            <a
              href="#faq"
              className="hidden text-sm font-medium text-[var(--_muted-fg)] transition-colors hover:text-[var(--_primary)] sm:block"
            >
              FAQ
            </a>
            <span className="hidden h-4 w-px bg-[var(--_border)] sm:block" aria-hidden="true" />
            <ThemeToggle />
            <button
              type="button"
              onClick={openWizard}
              aria-label="Plan a trip"
              className="btn btn-primary gap-2 rounded-xl px-3 py-2 sm:px-4"
            >
              <Plane size={14} aria-hidden="true" />
              <span className="hidden sm:inline">Plan a trip</span>
            </button>
            <span className="hidden h-4 w-px bg-[var(--_border)] sm:block" aria-hidden="true" />
            <UserMenu />
          </nav>
        </div>
      </header>

      {/* ── Hero ─────────────────────────────────────────────────── */}
      <main id="main-content">
        <section
          aria-labelledby="hero-heading"
          className="flex flex-col items-center px-4 pb-10 pt-10 text-center sm:px-6 sm:pt-14"
        >
          {/* SEO eyebrow — crawlable brand + keyword signal */}
          <p className="mb-3 text-xs font-bold uppercase tracking-[0.18em] text-[var(--_primary)] [font-family:var(--font-dm-sans)]">
            Wanderplanner · Free AI Travel Planner
          </p>

          {/* Primary H1 — above-fold, keyword-rich */}
          <h1
            id="hero-heading"
            className="font-display mx-auto max-w-3xl text-4xl font-black leading-[1.05] tracking-tight text-[var(--_fg)] sm:text-5xl lg:text-6xl"
          >
            Plan any trip in{' '}
            <span className="text-[var(--_primary)]">minutes,</span>
            <br />
            not hours.
          </h1>

          <p className="mx-auto mt-5 max-w-lg text-base leading-relaxed text-[var(--_muted-fg)] [font-family:var(--font-dm-sans)]">
            Tell{' '}
            <strong className="font-semibold text-[var(--_fg)]">Anya</strong>
            {' — '}Wanderplanner's AI concierge — your destination, budget, and group.
            Get a complete day-by-day itinerary in under a minute.
          </p>

          {/* Primary CTA */}
          <button
            type="button"
            onClick={openWizard}
            className="btn btn-accent mt-8 gap-3 rounded-2xl px-8 py-4 text-base font-bold shadow-lg"
            style={{ minHeight: '52px' }}
            aria-label="Start planning your trip with Anya, Wanderplanner's AI concierge"
          >
            Start planning with Anya
            <ArrowRight size={18} />
          </button>

          {/* ── Start Anywhere ── */}
          <div className="mt-6 w-full max-w-lg">
            <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-[var(--_muted-fg)]">
              Or start from a blog, Reddit post, or notes
            </p>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--_muted-fg)]">
                  <Link2 size={15} />
                </span>
                <input
                  type="text"
                  value={startInput}
                  onChange={(e) => setStartInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleStartAnywhere()}
                  placeholder="Paste a URL or describe where you want to go…"
                  className="input w-full rounded-xl border border-[var(--_border)] bg-[var(--_card)] py-2.5 text-sm text-[var(--_fg)] placeholder:text-[var(--_muted-fg)] focus:border-[var(--_primary)] focus:outline-none"
                  style={{ paddingLeft: '2.25rem' }}
                  aria-label="Paste a travel URL or text to start from"
                />
              </div>
              <button
                type="button"
                onClick={handleStartAnywhere}
                disabled={extracting}
                className="flex items-center gap-1.5 rounded-xl bg-[var(--_primary)] px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {extracting ? <Loader2 size={15} className="animate-spin" /> : <Plane size={15} />}
                {extracting ? 'Reading…' : 'Go'}
              </button>
            </div>
            {extractError && (
              <p className="mt-1.5 text-xs text-[var(--_muted-fg)]">{extractError}</p>
            )}
          </div>
        </section>

        {/* ── Inspiration gallery ──────────────────────────────────── */}
        <section
          id="inspiration"
          aria-labelledby="inspiration-heading"
          className="border-t border-[var(--_border)] bg-[var(--_bg)] px-6 py-14 scroll-mt-16"
        >
          <div className="mx-auto max-w-6xl">
            <div className="mb-6 flex items-end justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-[var(--_primary)]">
                  Inspiration
                </p>
                <h2
                  id="inspiration-heading"
                  className="font-display mt-1 text-2xl font-bold text-[var(--_fg)]"
                >
                  Popular trip ideas
                </h2>
              </div>
              <button
                type="button"
                onClick={openWizard}
                className="hidden text-sm font-medium text-[var(--_primary)] hover:underline sm:block"
              >
                Plan a custom trip →
              </button>
            </div>

            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {FEATURED_TRIPS.map((t) => (
                <InspirationCard key={t.dest} trip={t} onPlan={openWizardWithPreload} />
              ))}
            </div>
          </div>
        </section>

        {/* ── FAQ — crawlable by Google, matches JSON-LD ────────────── */}
        <section
          id="faq"
          aria-labelledby="faq-heading"
          className="border-t border-[var(--_border)] bg-[var(--_bg)] px-6 py-14 scroll-mt-16"
        >
          <div className="mx-auto max-w-2xl">
            <h2
              id="faq-heading"
              className="font-display mb-8 text-2xl font-bold text-[var(--_fg)]"
            >
              Frequently asked questions
            </h2>
            <dl className="space-y-6">
              {[
                {
                  q: 'Is Wanderplanner free?',
                  a: 'Yes — completely free. Just a free sign-up to get started, no credit card, no catch.',
                },
                {
                  q: 'How does Wanderplanner generate itineraries?',
                  a: 'Wanderplanner uses Google Gemini AI combined with real traveller data from Reddit and Wikivoyage to build personalised day-by-day plans with activities, costs, and local tips.',
                },
                {
                  q: 'Which destinations does Wanderplanner support?',
                  a: 'Wanderplanner covers 190+ countries — Bali, Paris, Dubai, Tokyo, Rajasthan, New York, and thousands more.',
                },
                {
                  q: 'Can it plan group or family trips?',
                  a: "Yes. Just tell Anya who's coming — solo, couple, family with kids, or a large group — and the itinerary is tailored accordingly.",
                },
              ].map(({ q, a }) => (
                <div key={q}>
                  <dt className="font-display text-sm font-bold text-[var(--_fg)]">{q}</dt>
                  <dd className="mt-1 text-sm leading-relaxed text-[var(--_muted-fg)] [font-family:var(--font-dm-sans)]">
                    {a}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        {/* ── Bottom CTA ──────────────────────────────────────────── */}
        <footer
          className="border-t border-[var(--_border)] bg-[var(--_primary)] px-6 py-12 text-center"
          aria-label="Call to action"
        >
          <WanderplannerLogo size="md" inverted wordmark />
          <p className="font-display mt-4 text-2xl font-bold text-white">
            Where are you headed next?
          </p>
          <p className="mt-2 text-sm text-white/70 [font-family:var(--font-dm-sans)]">
            Free to use · Free sign-up · Powered by Gemini AI
          </p>
          <button
            type="button"
            onClick={openWizard}
            className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-white px-8 py-3.5 text-sm font-bold text-[var(--_primary)] shadow transition-opacity hover:opacity-90"
          >
            Plan my trip <ArrowRight size={16} />
          </button>
          <p className="mt-8 text-xs text-white/40 [font-family:var(--font-dm-sans)]">
            © {new Date().getFullYear()} Wanderplanner · AI-assisted travel planning
          </p>
        </footer>
      </main>
    </div>
  )
}
