import type { Metadata } from 'next'
import Link from 'next/link'
import { WanderplannerLogo } from '@/components/common/WanderplannerLogo'

export const metadata: Metadata = {
  title: 'Terms of Service',
  description: 'Wanderplanner Terms of Service.',
}

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-[var(--_bg)] px-4 py-12">
      <div className="mx-auto max-w-3xl">
        <Link href="/" className="mb-8 inline-block">
          <WanderplannerLogo size="sm" />
        </Link>

        <div className="rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-8 shadow-sm">
          <h1 className="text-2xl font-bold text-[var(--_fg)] [font-family:var(--font-display)]">Terms of Service</h1>
          <p className="mt-1 text-sm text-[var(--_muted-fg)]">Last updated: July 2026</p>

          <div className="prose-legal mt-6 space-y-6 text-sm leading-relaxed text-[var(--_muted-fg)]">
            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">1. Acceptance of terms</h2>
              <p>
                By creating an account and using Wanderplanner ("we", "us", "our"), you agree to these Terms of
                Service and our{' '}
                <Link href="/privacy" className="font-medium text-[var(--_primary)] hover:underline">
                  Privacy Policy
                </Link>
                . If you do not agree, please do not use the service.
              </p>
            </section>

            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">2. Account &amp; sign-up</h2>
              <p>
                Wanderplanner is free to use and requires a free account to generate an itinerary. You may sign up
                with an email address and password, or with your Google account. You are responsible for keeping
                your login credentials secure and for all activity under your account.
              </p>
            </section>

            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">3. Acceptable use</h2>
              <p>
                You agree not to misuse the service — including attempting to bypass rate limits, scrape the service
                at scale, submit unlawful or abusive content to our AI assistant Anya, or interfere with other users'
                access to the service.
              </p>
            </section>

            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">4. AI-generated content</h2>
              <p>
                Itineraries, recommendations, and travel tips are generated with the help of AI (including Google
                Gemini) and third-party data sources. While we aim for accuracy, AI-generated content may contain
                errors — always verify critical details (visa requirements, opening hours, prices, safety advisories)
                independently before you travel.
              </p>
            </section>

            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">5. Account deletion</h2>
              <p>
                You may delete your account and associated personal data at any time from your account settings.
                See our{' '}
                <Link href="/privacy" className="font-medium text-[var(--_primary)] hover:underline">
                  Privacy Policy
                </Link>{' '}
                for details on what is deleted and what is retained in anonymized form.
              </p>
            </section>

            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">6. Changes to these terms</h2>
              <p>
                We may update these terms from time to time. Continued use of Wanderplanner after changes take
                effect constitutes acceptance of the revised terms.
              </p>
            </section>

            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">7. Contact</h2>
              <p>
                Questions about these terms can be sent to{' '}
                <a href="mailto:support@wanderplanner.app" className="font-medium text-[var(--_primary)] hover:underline">
                  support@wanderplanner.app
                </a>
                .
              </p>
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}
