'use client'

import { Users, Wallet, MapPin, Sparkles, ArrowRight, Plane } from 'lucide-react'
import { useAppStore } from '@/store/appStore'
import { WanderplanLogo } from '@/components/common/WanderplanLogo'
import { ThemeToggle } from '@/components/common/ThemeToggle'

const EXAMPLE_TRIPS = [
  { emoji: '🏖️', label: '7 days in Bali', sub: 'Beach + temples · ₹80,000' },
  { emoji: '🗼', label: 'Europe in 14 days', sub: 'Family of 4 · ₹3L budget' },
  { emoji: '🌆', label: 'Dubai long weekend', sub: 'Group of 8 · Luxury stay' },
  { emoji: '🏰', label: 'Rajasthan heritage tour', sub: '10 days · Couple trip' },
]

const FEATURED_TRIPS = [
  { emoji: '🏖️', dest: 'Bali, Indonesia',    days: 7,  budget: '₹80,000',   theme: 'Beach & Temples',      gradient: 'linear-gradient(135deg,#0EA5E9 0%,#0C4A6E 100%)' },
  { emoji: '🗼', dest: 'Paris, France',       days: 5,  budget: '₹1,80,000', theme: 'Romance & Culture',    gradient: 'linear-gradient(135deg,#DB2777 0%,#831843 100%)' },
  { emoji: '🏰', dest: 'Rajasthan, India',    days: 10, budget: '₹60,000',   theme: 'Heritage & Forts',     gradient: 'linear-gradient(135deg,#D4AF37 0%,#9A3412 100%)' },
  { emoji: '🌃', dest: 'Dubai, UAE',          days: 4,  budget: '₹1,20,000', theme: 'Luxury City Break',    gradient: 'linear-gradient(135deg,#EA580C 0%,#9A3412 100%)' },
  { emoji: '⛩️', dest: 'Kyoto, Japan',        days: 7,  budget: '₹2,00,000', theme: 'Culture & Zen',        gradient: 'linear-gradient(135deg,#DC2626 0%,#7F1D1D 100%)' },
  { emoji: '🦁', dest: 'Kenya Safari',        days: 8,  budget: '₹3,50,000', theme: 'Wildlife & Nature',    gradient: 'linear-gradient(135deg,#059669 0%,#065F46 100%)' },
  { emoji: '🏔️', dest: 'Himachal Pradesh',   days: 6,  budget: '₹45,000',   theme: 'Mountains & Treks',    gradient: 'linear-gradient(135deg,#7C3AED 0%,#1E3A5F 100%)' },
  { emoji: '🌊', dest: 'Maldives',            days: 5,  budget: '₹2,50,000', theme: 'Overwater & Snorkel',  gradient: 'linear-gradient(135deg,#06B6D4 0%,#0C4A6E 100%)' },
  { emoji: '🌆', dest: 'Singapore',           days: 4,  budget: '₹1,00,000', theme: 'Food & Skyline',       gradient: 'linear-gradient(135deg,#0EA5E9 0%,#7C3AED 100%)' },
  { emoji: '🏝️', dest: 'Andaman Islands',    days: 6,  budget: '₹70,000',   theme: 'Beaches & Diving',     gradient: 'linear-gradient(135deg,#10B981 0%,#0C4A6E 100%)' },
  { emoji: '🗽', dest: 'New York, USA',       days: 7,  budget: '₹2,80,000', theme: 'Iconic City Life',     gradient: 'linear-gradient(135deg,#1E40AF 0%,#0F172A 100%)' },
  { emoji: '🌸', dest: 'Bangkok, Thailand',  days: 5,  budget: '₹55,000',   theme: 'Street Food & Temples',gradient: 'linear-gradient(135deg,#F59E0B 0%,#DC2626 100%)' },
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

export function LandingHero() {
  const openWizard = useAppStore((s) => s.openWizard)

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-[var(--_bg)]">

      {/* ── Site nav ─────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 border-b border-[var(--_border)] bg-[var(--_bg)]/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <WanderplanLogo size="md" wordmark />
          <nav className="flex items-center gap-4" aria-label="Site navigation">
            <span className="hidden text-sm font-medium text-[var(--_muted-fg)] sm:block">
              Free · No sign-up
            </span>
            <ThemeToggle />
            <button
              type="button"
              onClick={openWizard}
              className="btn btn-primary gap-2 rounded-xl px-4 py-2"
            >
              <Plane size={14} />
              Plan a trip
            </button>
          </nav>
        </div>
      </header>

      {/* ── Hero ─────────────────────────────────────────────────── */}
      <main id="main-content">
        <section
          aria-labelledby="hero-heading"
          className="flex flex-col items-center px-6 pb-10 pt-14 text-center"
        >
          {/* SEO eyebrow — crawlable brand + keyword signal */}
          <p className="mb-3 text-xs font-bold uppercase tracking-[0.18em] text-[var(--_primary)] [font-family:var(--font-dm-sans)]">
            Wanderplan · Free AI Travel Planner
          </p>

          {/* Primary H1 — above-fold, keyword-rich */}
          <h1
            id="hero-heading"
            className="font-display mx-auto max-w-3xl text-5xl font-black leading-[1.05] tracking-tight text-[var(--_fg)] lg:text-6xl"
          >
            Plan any trip in{' '}
            <span className="text-[var(--_primary)]">minutes,</span>
            <br />
            not hours.
          </h1>

          <p className="mx-auto mt-5 max-w-lg text-base leading-relaxed text-[var(--_muted-fg)] [font-family:var(--font-dm-sans)]">
            Tell{' '}
            <strong className="font-semibold text-[var(--_fg)]">Anya</strong>
            {' — '}Wanderplan's AI concierge — your destination, budget, and group.
            Get a complete day-by-day itinerary in under a minute.
          </p>

          {/* Primary CTA */}
          <button
            type="button"
            onClick={openWizard}
            className="btn btn-accent mt-8 gap-3 rounded-2xl px-8 py-4 text-base font-bold shadow-lg"
            style={{ minHeight: '52px' }}
            aria-label="Start planning your trip with Anya, Wanderplan's AI concierge"
          >
            Start planning with Anya
            <ArrowRight size={18} />
          </button>

          {/* Example trip cards — visually clickable */}
          <div
            className="mt-8 grid w-full max-w-3xl grid-cols-2 gap-3 lg:grid-cols-4"
            role="list"
            aria-label="Example trips"
          >
            {EXAMPLE_TRIPS.map((t) => (
              <button
                key={t.label}
                type="button"
                role="listitem"
                onClick={openWizard}
                aria-label={`Plan a trip: ${t.label}, ${t.sub}`}
                className="group cursor-pointer rounded-2xl border border-[var(--_border)] bg-[var(--_card)] px-4 py-3.5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-[var(--_primary)] hover:shadow-md dark:hover:border-[var(--_primary)]"
              >
                <span className="mb-1.5 block text-xl" aria-hidden="true">{t.emoji}</span>
                <span className="block text-sm font-bold text-[var(--_fg)] [font-family:var(--font-space-grotesk)]">
                  {t.label}
                </span>
                <span className="mt-0.5 block text-xs text-[var(--_muted-fg)] [font-family:var(--font-dm-sans)]">
                  {t.sub}
                </span>
                <span className="mt-2 flex items-center gap-1 text-xs font-semibold text-[var(--_primary)] opacity-0 transition-opacity group-hover:opacity-100">
                  Plan this <ArrowRight size={11} />
                </span>
              </button>
            ))}
          </div>
        </section>

        {/* ── Feature grid ─────────────────────────────────────────── */}
        <section
          aria-label="Wanderplan features"
          className="border-t border-[var(--_border)] bg-[var(--_card)] px-6 py-14"
        >
          <h2 className="sr-only">Why use Wanderplan</h2>
          <div className="mx-auto grid max-w-4xl grid-cols-2 gap-8 lg:grid-cols-4">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="flex flex-col gap-3">
                <span
                  className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--_primary)]/10 text-[var(--_primary)]"
                  aria-hidden="true"
                >
                  <Icon size={20} />
                </span>
                <h3 className="font-display text-sm font-bold text-[var(--_fg)]">{title}</h3>
                <p className="text-sm leading-relaxed text-[var(--_muted-fg)] [font-family:var(--font-dm-sans)]">
                  {desc}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Inspiration gallery ──────────────────────────────────── */}
        <section
          aria-labelledby="inspiration-heading"
          className="border-t border-[var(--_border)] bg-[var(--_bg)] px-6 py-14"
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
                <button
                  key={t.dest}
                  type="button"
                  onClick={openWizard}
                  className="group cursor-pointer overflow-hidden rounded-2xl border border-[var(--_border)] bg-[var(--_card)] text-left shadow-sm transition-all hover:-translate-y-1 hover:border-[var(--_primary)] hover:shadow-lg"
                  aria-label={`Start planning: ${t.dest}, ${t.days} days, ${t.budget}`}
                >
                  {/* Gradient hero */}
                  <div
                    className="relative flex h-28 w-full items-end p-3"
                    style={{ background: t.gradient }}
                  >
                    <span className="absolute right-3 top-3 text-2xl">{t.emoji}</span>
                    <span className="rounded-full bg-black/30 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white/90 backdrop-blur-sm">
                      {t.theme}
                    </span>
                  </div>
                  {/* Caption */}
                  <div className="px-3 pb-3 pt-2">
                    <p className="text-sm font-bold text-[var(--_fg)] leading-tight">{t.dest}</p>
                    <p className="mt-0.5 text-xs text-[var(--_muted-fg)]">
                      {t.days} days · {t.budget}
                    </p>
                    <span className="mt-2 inline-flex items-center gap-0.5 text-xs font-semibold text-[var(--_primary)] opacity-0 transition-opacity group-hover:opacity-100">
                      Plan this <ArrowRight size={11} />
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* ── FAQ — crawlable by Google, matches JSON-LD ────────────── */}
        <section
          aria-labelledby="faq-heading"
          className="border-t border-[var(--_border)] bg-[var(--_bg)] px-6 py-14"
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
                  q: 'Is Wanderplan free?',
                  a: 'Yes — completely free. No sign-up, no credit card, no catch.',
                },
                {
                  q: 'How does Wanderplan generate itineraries?',
                  a: 'Wanderplan uses Google Gemini AI combined with real traveller data from Reddit and Wikivoyage to build personalised day-by-day plans with activities, costs, and local tips.',
                },
                {
                  q: 'Which destinations does Wanderplan support?',
                  a: 'Wanderplan covers 190+ countries — Bali, Paris, Dubai, Tokyo, Rajasthan, New York, and thousands more.',
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
          <WanderplanLogo size="md" inverted wordmark />
          <p className="font-display mt-4 text-2xl font-bold text-white">
            Where are you headed next?
          </p>
          <p className="mt-2 text-sm text-white/70 [font-family:var(--font-dm-sans)]">
            Free to use · No account · Powered by Gemini AI
          </p>
          <button
            type="button"
            onClick={openWizard}
            className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-white px-8 py-3.5 text-sm font-bold text-[var(--_primary)] shadow transition-opacity hover:opacity-90"
          >
            Plan my trip <ArrowRight size={16} />
          </button>
          <p className="mt-8 text-xs text-white/40 [font-family:var(--font-dm-sans)]">
            © {new Date().getFullYear()} Wanderplan · AI-assisted travel planning
          </p>
        </footer>
      </main>
    </div>
  )
}
