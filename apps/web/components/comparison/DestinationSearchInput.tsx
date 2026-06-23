'use client'

import { useEffect, useRef, useState } from 'react'
import { geocode } from '@/lib/api'
import type { DestinationInput } from '@/types'

interface Props {
  label: string
  value: DestinationInput | null
  onChange: (dest: DestinationInput) => void
}

interface GeocodeSuggestion {
  display_name: string
  lat: number
  lon: number
  country_code: string
}

export function DestinationSearchInput({ label, value, onChange }: Props) {
  const [query, setQuery] = useState(value?.city ?? '')
  const [suggestions, setSuggestions] = useState<GeocodeSuggestion[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (query.length < 2) { setSuggestions([]); return }
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const result = await geocode(query)
        setSuggestions([result])
        setOpen(true)
      } catch {
        setSuggestions([])
      } finally {
        setLoading(false)
      }
    }, 400)
  }, [query])

  function handleSelect(s: GeocodeSuggestion) {
    // Use the first segment of display_name (already English from backend)
    const city = s.display_name.split(',')[0].trim()
    setQuery(city)
    setOpen(false)
    onChange({ city, country: s.country_code.toUpperCase(), lat: s.lat, lon: s.lon })
  }

  return (
    <div className="relative">
      <label className="mb-1 block text-xs font-medium text-[var(--_muted-fg)]">{label}</label>
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder="City, country…"
          className="input"
        />
        {loading && (
          <span className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin rounded-full border-2 border-[var(--_primary)] border-t-transparent" />
        )}
      </div>
      {open && suggestions.length > 0 && (
        <ul className="absolute left-0 right-0 z-50 mt-1 overflow-hidden rounded-xl border border-[var(--_border)] bg-[var(--_card)] shadow-lg">
          {suggestions.map((s, i) => (
            <li
              key={i}
              onMouseDown={() => handleSelect(s)}
              className="cursor-pointer border-b border-[var(--_border)] px-3 py-2.5 text-sm text-[var(--_fg)] last:border-0 hover:bg-[var(--_muted)]"
            >
              {s.display_name}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
