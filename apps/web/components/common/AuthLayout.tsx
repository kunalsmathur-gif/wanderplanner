'use client'

import { WanderplannerLogo } from '@/components/common/WanderplannerLogo'
import Link from 'next/link'

interface Props {
  title: string
  subtitle: string
  children: React.ReactNode
  footer?: React.ReactNode
}

/** Shared centered-card shell for /login, /signup, /forgot-password,
 * /reset-password — matches the design tokens used across the rest of the
 * app (card surface, border, radius, shadow, brand mark). */
export function AuthLayout({ title, subtitle, children, footer }: Props) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[var(--_bg)] px-4 py-6 sm:py-12">
      <Link href="/" className="mb-4 sm:mb-8">
        <WanderplannerLogo size="md" />
      </Link>

      <div className="w-full max-w-md rounded-2xl border border-[var(--_border)] bg-[var(--_card)] p-5 shadow-lg sm:p-8">
        <h1 className="text-center text-xl font-bold text-[var(--_fg)] [font-family:var(--font-display)] sm:text-2xl">
          {title}
        </h1>
        <p className="mt-1.5 text-center text-sm text-[var(--_muted-fg)]">{subtitle}</p>

        <div className="mt-4 sm:mt-6">{children}</div>
      </div>

      {footer && <div className="mt-4 text-center text-sm text-[var(--_muted-fg)] sm:mt-6">{footer}</div>}
    </div>
  )
}
