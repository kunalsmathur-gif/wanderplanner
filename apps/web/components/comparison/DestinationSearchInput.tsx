'use client'

import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { geocode } from '@/lib/api'
import { MAX_CITY_LEN } from '@/lib/limits'
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
  const inputId = useId()
  const listboxId = `${inputId}-listbox`
  const [query, setQuery] = useState(value?.city ?? '')
  const [suggestions, setSuggestions] = useState<GeocodeSuggestion[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState<number>(-1)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (query.length < 2) {
      setSuggestions([])
      setOpen(false)
      setHighlightedIndex(-1)
      return
    }
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const result = await geocode(query)
        setSuggestions([result])
        setOpen(true)
        setHighlightedIndex(0)
      } catch {
        setSuggestions([])
        setOpen(false)
        setHighlightedIndex(-1)
      } finally {
        setLoading(false)
      }
    }, 400)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query])

  function handleSelect(s: GeocodeSuggestion) {
    const city = s.display_name.split(',')[0].trim()
    setQuery(city)
    setOpen(false)
    setHighlightedIndex(-1)
    onChange({ city, country: s.country_code.toUpperCase(), lat: s.lat, lon: s.lon })
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!suggestions.length) {
      if (event.key === 'Escape') setOpen(false)
      return
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setOpen(true)
      setHighlightedIndex((current) => (current + 1 + suggestions.length) % suggestions.length)
      return
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setOpen(true)
      setHighlightedIndex((current) => (current - 1 + suggestions.length) % suggestions.length)
      return
    }

    if (event.key === 'Enter' && open && highlightedIndex >= 0) {
      event.preventDefault()
      handleSelect(suggestions[highlightedIndex])
      return
    }

    if (event.key === 'Escape') {
      event.preventDefault()
      setOpen(false)
      setHighlightedIndex(-1)
    }
  }

  return (
    <div className="relative">
      <label htmlFor={inputId} className="mb-1 block text-xs font-medium text-[var(--_muted-fg)]">{label}</label>
      <div className="relative">
        <input
          id={inputId}
          type="text"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-activedescendant={open && highlightedIndex >= 0 ? `${inputId}-option-${highlightedIndex}` : undefined}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          onBlur={() => setTimeout(() => {
            setOpen(false)
            setHighlightedIndex(-1)
          }, 150)}
          onKeyDown={handleKeyDown}
          placeholder="City, country…"
          maxLength={MAX_CITY_LEN}
          className="input"
        />
        {loading && (
          <span className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin rounded-full border-2 border-[var(--_primary)] border-t-transparent" />
        )}
      </div>
      {open && suggestions.length > 0 && (
        <ul
          id={listboxId}
          role="listbox"
          className="absolute left-0 right-0 z-50 mt-1 overflow-hidden rounded-xl border border-[var(--_border)] bg-[var(--_card)] shadow-lg"
        >
          {suggestions.map((s, i) => {
            const isHighlighted = i === highlightedIndex

            return (
              <li
                key={`${s.display_name}-${i}`}
                id={`${inputId}-option-${i}`}
                role="option"
                aria-selected={isHighlighted}
                onMouseDown={() => handleSelect(s)}
                onMouseEnter={() => setHighlightedIndex(i)}
                className={[
                  'cursor-pointer border-b border-[var(--_border)] px-3 py-2.5 text-sm text-[var(--_fg)] last:border-0',
                  isHighlighted ? 'bg-[var(--_muted)]' : 'hover:bg-[var(--_muted)]',
                ].join(' ')}
              >
                {s.display_name}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
