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
        // Wrap single result into array for UI
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
    const city = s.display_name.split(',')[0].trim()
    setQuery(city)
    setOpen(false)
    onChange({ city, country: s.country_code.toUpperCase(), lat: s.lat, lon: s.lon })
  }

  return (
    <div className="relative">
      <label className="block text-xs font-medium text-slate-500 mb-1">{label}</label>
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          placeholder="City, country…"
          className="w-full h-10 px-3 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-[#1E40AF] bg-white"
        />
        {loading && (
          <span className="absolute right-3 top-2.5 w-4 h-4 border-2 border-[#1E40AF] border-t-transparent rounded-full animate-spin" />
        )}
      </div>
      {open && suggestions.length > 0 && (
        <ul className="absolute z-50 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg text-sm overflow-hidden">
          {suggestions.map((s, i) => (
            <li
              key={i}
              onClick={() => handleSelect(s)}
              className="px-3 py-2.5 cursor-pointer hover:bg-blue-50 text-slate-700 border-b border-slate-100 last:border-0"
            >
              {s.display_name}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
