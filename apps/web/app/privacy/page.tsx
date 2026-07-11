import type { Metadata } from 'next'
import Link from 'next/link'
import { WanderplannerLogo } from '@/components/common/WanderplannerLogo'

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'Wanderplanner Privacy Policy — what data we collect, why, and your rights.',
}

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-[var(--_bg)] px-4 py-12">
      <div className="mx-auto max-w-3xl">
        <Link href="/" className="mb-8 inline-block">
          <WanderplannerLogo size="sm" />
        </Link>

        <div className="rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-8 shadow-sm">
          <h1 className="text-2xl font-bold text-[var(--_fg)] [font-family:var(--font-display)]">Privacy Policy</h1>
          <p className="mt-1 text-sm text-[var(--_muted-fg)]">Last updated: July 2026</p>
          <p className="mt-4 text-sm leading-relaxed text-[var(--_muted-fg)]">
            This policy explains what personal data Wanderplanner ("we", "us", "our") collects when you create an
            account, why we collect it, and the rights you have over it — in line with India's Digital Personal Data
            Protection Act, 2023 (DPDP Act) and generally accepted global privacy practices.
          </p>

          <div className="mt-6 space-y-6 text-sm leading-relaxed text-[var(--_muted-fg)]">
            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">1. What we collect</h2>
              <ul className="mt-2 list-disc space-y-1.5 pl-5">
                <li><strong className="text-[var(--_fg)]">Account data:</strong> email address, a securely hashed password (we never store your password in plain text), and, if you use Google Sign-In, your Google name/profile info.</li>
                <li><strong className="text-[var(--_fg)]">Trip data:</strong> destinations, dates, budget, group details, and preferences you share with Anya to generate itineraries.</li>
                <li><strong className="text-[var(--_fg)]">Usage data:</strong> basic session and interaction events (e.g. sign-up, login, itinerary generation) used to operate and improve the service.</li>
              </ul>
            </section>

            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">2. Why we collect it</h2>
              <p>We process your personal data only for specific, informed purposes:</p>
              <ul className="mt-2 list-disc space-y-1.5 pl-5">
                <li>To create and secure your account and let you log back in across sessions.</li>
                <li>To personalize the itineraries, tips, and recommendations Anya generates for you.</li>
                <li>To send you service-related communications (e.g. password reset emails) — never marketing emails without separate opt-in.</li>
                <li>To monitor and improve service reliability and quality (aggregated, where possible anonymized, analytics).</li>
              </ul>
            </section>

            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">3. Who we share it with</h2>
              <p>We share the minimum data necessary with the following processors, solely to provide the service:</p>
              <ul className="mt-2 list-disc space-y-1.5 pl-5">
                <li><strong className="text-[var(--_fg)]">Google Gemini</strong> — to generate itineraries and travel tips from your trip inputs.</li>
                <li><strong className="text-[var(--_fg)]">Google OAuth</strong> — only if you choose "Continue with Google," to verify your identity.</li>
                <li><strong className="text-[var(--_fg)]">Pexels</strong> — to fetch royalty-free destination photos (no personal data sent).</li>
                <li><strong className="text-[var(--_fg)]">Resend</strong> — to deliver password-reset emails.</li>
              </ul>
              <p className="mt-2">We do not sell your personal data to any third party.</p>
            </section>

            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">4. How long we keep it</h2>
              <p>
                We retain your account data for as long as your account is active. If you delete your account, your
                personal data (email, password hash, name, Google identifier) is permanently deleted immediately.
                Aggregated usage events are retained in anonymized form (with no link back to you) for service
                analytics.
              </p>
            </section>

            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">5. Your rights</h2>
              <p>You have the right to:</p>
              <ul className="mt-2 list-disc space-y-1.5 pl-5">
                <li><strong className="text-[var(--_fg)]">Access</strong> the personal data we hold about you.</li>
                <li><strong className="text-[var(--_fg)]">Correct</strong> inaccurate account information.</li>
                <li><strong className="text-[var(--_fg)]">Erase</strong> your account and personal data at any time, instantly, from your account settings — or by writing to us.</li>
                <li><strong className="text-[var(--_fg)]">Withdraw consent</strong> at any time, which will result in your account being deactivated/deleted, since an account is required to use the service.</li>
              </ul>
            </section>

            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">6. Security</h2>
              <p>
                Passwords are hashed with Argon2id and never stored or logged in plain text. Sessions use short-lived,
                httpOnly, secure cookies. Data is encrypted in transit (TLS) and at rest via our database provider.
              </p>
            </section>

            <section>
              <h2 className="text-base font-semibold text-[var(--_fg)]">7. Grievance &amp; contact</h2>
              <p>
                For any privacy questions, data access/deletion requests, or grievances regarding how your personal
                data is processed, please contact our Grievance Officer at{' '}
                <a href="mailto:privacy@wanderplanner.app" className="font-medium text-[var(--_primary)] hover:underline">
                  privacy@wanderplanner.app
                </a>
                . We aim to respond within 30 days, in line with the DPDP Act's grievance redressal requirements.
              </p>
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}
