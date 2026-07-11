'use client'

import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'

export function ThemeToggle({ className }: { className?: string }) {
  const [isDark, setIsDark] = useState(false)

  useEffect(() => {
    const html = document.documentElement

    // Sync state on mount
    setIsDark(html.classList.contains('dark'))

    // Stay in sync if the class is changed anywhere (other toggle instance, etc.)
    const observer = new MutationObserver(() => {
      setIsDark(html.classList.contains('dark'))
    })
    observer.observe(html, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])

  function toggle() {
    const html = document.documentElement
    // Read LIVE DOM — avoids stale-closure race on React 19
    const next = !html.classList.contains('dark')
    html.classList.toggle('dark', next)
    try { localStorage.setItem('wp-theme', next ? 'dark' : 'light') } catch { /* ignore */ }
    // setIsDark handled by the MutationObserver above
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className={className ?? 'flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--_border)] text-[var(--_fg)] transition-colors hover:border-[var(--_primary)] hover:text-[var(--_primary)] focus-visible:outline-2 focus-visible:outline-[var(--_primary)]'}
    >
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  )
}
