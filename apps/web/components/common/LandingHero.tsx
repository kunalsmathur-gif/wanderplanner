'use client'

import { Users, Wallet, MapPin, Sparkles, ArrowRight } from 'lucide-react'
import { useAppStore } from '@/store/appStore'
import { WanderplanLogo } from '@/components/common/WanderplanLogo'

const EXAMPLE_TRIPS = [
  { label: '7 days in Bali', sub: 'Beach + temples, ₹80,000' },
  { label: 'Europe in 14 days', sub: 'Family of 4, ₹3L budget' },
  { label: 'Dubai long weekend', sub: 'Group of 8, luxury stay' },
  { label: 'Rajasthan heritage tour', sub: '10 days, couple trip' },
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

      {/* ── Hero section ─────────────────────────────────────────── */}
      <section className="flex flex-1 flex-col items-center justify-center px-6 py-20 text-center">

        {/* Badge */}
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-[var(--_border)] bg-[var(--_card)] px-4 py-1.5 text-sm font-medium text-[var(--_primary)]">
          <WanderplanLogo size="sm" wordmark={false} />
          Your AI travel concierge · No sign-up needed
        </div>

        {/* Headline */}
        <h1
          className="font-display mx-auto max-w-3xl text-5xl font-black leading-[1.05] tracking-tight text-[var(--_fg)] lg:text-6xl"
        >
          Plan any trip in{' '}
          <span className="text-[var(--_primary)]">minutes,</span>
          <br />
          not hours.
        </h1>

        <p className="mx-auto mt-6 max-w-xl text-lg text-[var(--_muted-fg)]">
          Tell Anya — Wanderplan's travel concierge — your destination, budget, and group.
          Get a full day-by-day itinerary with activities, bookings, and local tips.
        </p>

        {/* CTA */}
        <button
          type="button"
          onClick={openWizard}
          className="btn btn-accent mt-10 gap-3 rounded-2xl px-8 py-4 text-base font-bold shadow-lg"
          style={{ minHeight: '56px' }}
        >
          Plan with Anya, your concierge
          <ArrowRight size={18} />
        </button>

        {/* Example trip chips */}
        <div className="mt-8 flex flex-wrap justify-center gap-2">
          {EXAMPLE_TRIPS.map((t) => (
            <button
              key={t.label}
              type="button"
              onClick={openWizard}
              className="chip rounded-full px-4 py-2 text-sm"
            >
              <span className="font-semibold">{t.label}</span>
              <span className="ml-1.5 text-[var(--_muted-fg)]">{t.sub}</span>
            </button>
          ))}
        </div>
      </section>

      {/* ── Feature grid ─────────────────────────────────────────── */}
      <section className="border-t border-[var(--_border)] bg-[var(--_card)] px-6 py-16">
        <div className="mx-auto grid max-w-4xl grid-cols-2 gap-6 lg:grid-cols-4">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="flex flex-col gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--_muted)] text-[var(--_primary)]">
                <Icon size={20} />
              </span>
              <h3 className="font-display text-sm font-bold text-[var(--_fg)]">{title}</h3>
              <p className="text-sm leading-relaxed text-[var(--_muted-fg)]">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Bottom CTA ───────────────────────────────────────────── */}
      <section className="border-t border-[var(--_border)] bg-[var(--_primary)] px-6 py-12 text-center">
        <WanderplanLogo size="md" inverted wordmark />
        <p className="mt-4 font-display text-2xl font-bold text-white">
          Where are you headed next?
        </p>
        <p className="mt-2 text-sm text-white/70">
          Free to use · No account · Powered by Gemini AI
        </p>
        <button
          type="button"
          onClick={openWizard}
          className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-white px-8 py-3.5 text-sm font-bold text-[var(--_primary)] shadow transition-opacity hover:opacity-90"
        >
          Plan my trip <ArrowRight size={16} />
        </button>
      </section>

    </div>
  )
}
