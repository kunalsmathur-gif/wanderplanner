'use client'

import Link from 'next/link'

/** Segmented Sign up / Log in switcher pinned to the top of the auth card.
 * Returning users used to have to scan past the whole form to find the "Log
 * in" line under the card — this puts both routes at eye level before the
 * first field, and costs less vertical space than the old footer line. */
export function AuthSwitch({ active, returnTo }: { active: 'signup' | 'login'; returnTo: string }) {
  const qs = `?returnTo=${encodeURIComponent(returnTo)}`

  return (
    <nav
      aria-label="Sign up or log in"
      className="mb-4 grid grid-cols-2 gap-1 rounded-xl border border-[var(--_border)] bg-[var(--_bg)] p-1"
    >
      <SwitchLink href={`/signup${qs}`} isActive={active === 'signup'}>
        Sign up
      </SwitchLink>
      <SwitchLink href={`/login${qs}`} isActive={active === 'login'}>
        Log in
      </SwitchLink>
    </nav>
  )
}

function SwitchLink({ href, isActive, children }: { href: string; isActive: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={isActive ? 'page' : undefined}
      // Both labels stay at full --_fg contrast so the inactive route is easy
      // to read (--_muted-fg only clears ~4:1 on the light-mode track); the
      // active one is marked by the elevated pill + ring instead of by colour.
      className={`flex min-h-11 items-center justify-center rounded-lg text-sm font-semibold text-[var(--_fg)] transition-colors ${
        isActive
          ? 'bg-[var(--_card-elevated)] shadow-sm ring-1 ring-[var(--_border)]'
          : 'hover:bg-[var(--_card-elevated)]'
      }`}
    >
      {children}
    </Link>
  )
}
