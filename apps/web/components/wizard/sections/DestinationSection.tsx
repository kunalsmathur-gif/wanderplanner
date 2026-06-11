'use client'

import { useEffect, useRef, useState } from 'react'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { geocode } from '@/lib/api'
import type { DestinationInput } from '@/types'

const THEMES = ['🏖️ Beaches', '🏛️ Sights', '⛰️ Mountains', '🎶 Nightlife', '🦁 Wildlife', '💼 Work-Friendly']

export function DestinationSection() {
  const config = useTripConfigStore((s) => s.config)
  const updateConfig = useTripConfigStore((s) => s.updateConfig)
  const setOrigin = useTripConfigStore((s) => s.setOrigin)
  const setDestination = useTripConfigStore((s) => s.setDestination)

  return (
    <section className="space-y-4">
      <h2 className="text-base font-semibold text-[#0F172A]">Origin & Destination *</h2>

      {/* Scope */}
      <div className="flex gap-2">
        {(['local', 'domestic', 'international'] as const).map((scope) => (
          <button
            key={scope}
            onClick={() => updateConfig({ scope })}
            className={[
              'px-3 py-1.5 rounded-lg border text-sm capitalize transition-all',
              config.scope === scope
                ? 'bg-[#1E40AF] border-[#1E40AF] text-white'
                : 'bg-white border-slate-300 text-slate-700 hover:border-[#1E40AF]',
            ].join(' ')}
          >
            {scope}
          </button>
        ))}
      </div>

      {/* Origin — geocoded */}
      <GeoInput
        label="Origin city / airport *"
        placeholder="e.g. Bangalore, BLR"
        value={config.origin.city}
        onSelect={(city, lat, lon) => setOrigin({ ...config.origin, city, lat, lon })}
        onTextChange={(city) => setOrigin({ ...config.origin, city })}
      />

      {/* Destination mode */}
      <div className="flex gap-3">
        {(['fixed', 'exploring'] as const).map((mode) => (
          <button
            key={mode}
            onClick={() => updateConfig({ destination_mode: mode })}
            className={[
              'px-4 py-2 rounded-lg border text-sm font-medium transition-all',
              config.destination_mode === mode
                ? 'bg-[#1E40AF] border-[#1E40AF] text-white'
                : 'bg-white border-slate-300 text-slate-700 hover:border-[#1E40AF]',
            ].join(' ')}
          >
            {mode === 'fixed' ? '📍 Fixed Destination' : '🔍 Exploring Options'}
          </button>
        ))}
      </div>

      {config.destination_mode === 'fixed' ? (
        <GeoInput
          label="Destination city"
          placeholder="e.g. Kuala Lumpur, Malaysia"
          value={config.destination?.city ?? ''}
          onSelect={(city, lat, lon) =>
            setDestination({ city, country: '', lat, lon } satisfies DestinationInput)
          }
          onTextChange={(city) =>
            setDestination(city ? { city, country: '', lat: 0, lon: 0 } : null)
          }
        />
      ) : (
        <div className="flex flex-wrap gap-2">
          {THEMES.map((theme) => {
            const id = theme.split(' ').slice(1).join(' ').toLowerCase()
            const selected = config.themes.includes(id)
            return (
              <button
                key={id}
                onClick={() =>
                  updateConfig({
                    themes: selected
                      ? config.themes.filter((t) => t !== id)
                      : [...config.themes, id],
                  })
                }
                className={[
                  'px-3 py-1.5 rounded-lg border text-sm transition-all',
                  selected
                    ? 'bg-[#1E40AF] border-[#1E40AF] text-white'
                    : 'bg-white border-slate-300 text-slate-700 hover:border-[#1E40AF]',
                ].join(' ')}
              >
                {theme}
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}

// Reusable geocoded text input
interface GeoInputProps {
  label: string
  placeholder: string
  value: string
  onSelect: (city: string, lat: number, lon: number) => void
  onTextChange: (city: string) => void
}

function GeoInput({ label, placeholder, value, onSelect, onTextChange }: GeoInputProps) {
  const [text, setText] = useState(value)
  const [suggestion, setSuggestion] = useState<{ city: string; lat: number; lon: number } | null>(null)
  const [loading, setLoading] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync external value resets (e.g. form reset)
  useEffect(() => { setText(value) }, [value])

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value
    setText(v)
    onTextChange(v)
    setSuggestion(null)

    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (v.length < 3) return
    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const result = await geocode(v)
        const city = result.display_name.split(',')[0].trim()
        setSuggestion({ city, lat: result.lat, lon: result.lon })
      } catch { /* silent */ } finally {
        setLoading(false)
      }
    }, 500)
  }

  function handleAccept() {
    if (!suggestion) return
    setText(suggestion.city)
    onSelect(suggestion.city, suggestion.lat, suggestion.lon)
    setSuggestion(null)
  }

  return (
    <div>
      <label className="block text-xs text-slate-500 mb-1">{label}</label>
      <div className="relative">
        <input
          type="text"
          value={text}
          onChange={handleChange}
          placeholder={placeholder}
          className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1E40AF]"
        />
        {loading && (
          <span className="absolute right-3 top-2.5 w-3 h-3 border-2 border-[#1E40AF] border-t-transparent rounded-full animate-spin" />
        )}
      </div>
      {suggestion && (
        <button
          type="button"
          onClick={handleAccept}
          className="mt-1 w-full text-left px-3 py-2 text-xs bg-blue-50 border border-blue-200 rounded-lg text-blue-700 hover:bg-blue-100 transition-colors"
        >
          📍 {suggestion.city} — click to confirm location
        </button>
      )}
    </div>
  )
}
