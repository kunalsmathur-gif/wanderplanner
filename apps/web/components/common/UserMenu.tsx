'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { LogOut, User, ChevronDown, ShieldCheck } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'

/**
 * Auth-aware nav control — shows "Log in / Sign up" when signed out, or the
 * user's name/email with a dropdown (Account, Log out) when signed in.
 * Meant to be dropped into any top-of-page nav bar.
 */
export function UserMenu({ inverted = false }: { inverted?: boolean }) {
  const router = useRouter()
  const status = useAuthStore((s) => s.status)
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)

  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const mutedClass = inverted ? 'text-white/70 hover:text-white' : 'text-[var(--_muted-fg)] hover:text-[var(--_primary)]'

  if (status === 'loading' || status === 'idle') {
    return <span className={`h-9 w-20 animate-pulse rounded-lg ${inverted ? 'bg-white/10' : 'bg-[var(--_border)]'}`} aria-hidden="true" />
  }

  if (status === 'unauthenticated' || !user) {
    return (
      <div className="flex items-center gap-1.5 sm:gap-3">
        <Link href="/login" className={`hidden whitespace-nowrap text-sm font-medium transition-colors sm:block ${mutedClass}`}>
          Log in
        </Link>
        <Link href="/signup" className="btn btn-primary whitespace-nowrap rounded-xl px-3 py-2 text-sm font-semibold sm:px-4">
          Sign up
        </Link>
      </div>
    )
  }

  const label = user.display_name || user.email || 'Account'

  async function handleLogout() {
    setOpen(false)
    await logout()
    router.push('/')
  }

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Signed in as ${label}`}
        className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-sm font-medium transition-colors ${
          inverted
            ? 'border-white/20 text-white/90 hover:border-white/40'
            : 'border-[var(--_border)] text-[var(--_fg)] hover:border-[var(--_primary)]'
        }`}
      >
        <User size={14} aria-hidden="true" />
        <span className="max-w-[10rem] truncate">{label}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-20 mt-2 w-48 overflow-hidden rounded-xl border border-[var(--_border)] bg-[var(--_card)] py-1 shadow-lg"
        >
          <div className="border-b border-[var(--_border)] px-3 py-2">
            <p className="truncate text-xs font-semibold text-[var(--_fg)]">{label}</p>
            {user.email && user.display_name && (
              <p className="truncate text-[11px] text-[var(--_muted-fg)]">{user.email}</p>
            )}
          </div>
          <Link
            href="/account"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="block px-3 py-2 text-sm text-[var(--_fg)] transition-colors hover:bg-[var(--_bg)]"
          >
            Account settings
          </Link>
          {user.is_admin && (
            <Link
              href="/admin"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3 py-2 text-sm text-[var(--_fg)] transition-colors hover:bg-[var(--_bg)]"
            >
              <ShieldCheck size={14} aria-hidden="true" />
              Admin console
            </Link>
          )}
          <button
            type="button"
            role="menuitem"
            onClick={handleLogout}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-red-500 transition-colors hover:bg-[var(--_bg)]"
          >
            <LogOut size={14} aria-hidden="true" />
            Log out
          </button>
        </div>
      )}
    </div>
  )
}
