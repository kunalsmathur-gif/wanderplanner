'use client'

import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'

export function ThemeToggle() {
  const [isDark, setIsDark] = useState(false)

  useEffect(() => {
    setIsDark(document.documentElement.classList.contains('dark'))
  }, [])

  function toggle() {
    const next = !isDark
    setIsDark(next)
    document.documentElement.classList.toggle('dark', next)
    try {
      localStorage.setItem('wp-theme', next ? 'dark' : 'light')
    } catch {
      // ignore
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/20 transition-colors hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white/60"
    >
      {isDark
        ? <Sun  size={16} className="text-white/90" />
        : <Moon size={16} className="text-white/90" />}
    </button>
  )
}
