'use client'

import { useEffect, useRef, useState } from 'react'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { geocode, recommendCities } from '@/lib/api'
import type { DestinationInput, DestinationMode, RecommendedCity } from '@/types'

const THEMES = ['🏖️ Beaches', '🏛️ Sights', '⛰️ Mountains', '🎶 Nightlife', '🦁 Wildlife', '💼 Work-Friendly']

export function DestinationSection() {
  const config = useTripConfigStore((s) => s.config)
  const updateConfig = useTripConfigStore((s) => s.updateConfig)
  const setOrigin = useTripConfigStore((s) => s.setOrigin)
  const setDestination = useTripConfigStore((s) => s.setDestination)
  const addHop = useTripConfigStore((s) => s.addHop)
  const removeHop = useTripConfigStore((s) => s.removeHop)

  // Country-mode state
  const [countryInput, setCountryInput] = useState('')
  const [cityRecs, setCityRecs] = useState<RecommendedCity[]>([])
  const [recLoading, setRecLoading] = useState(false)
  const [selectedRecs, setSelectedRecs] = useState<Set<number>>(new Set())

  async function handleGetCityRecs() {
    if (!countryInput.trim()) return
    setRecLoading(true)
    setCityRecs([])
    setSelectedRecs(new Set())
    try {
      const res = await recommendCities(countryInput.trim(), config)
      setCityRecs(res.cities)
    } catch { /* silent */ } finally {
      setRecLoading(false)
    }
  }

  function toggleRec(i: number) {
    setSelectedRecs((prev) => {
      const next = new Set(prev)
      if (next.has(i)) { next.delete(i) } else { next.add(i) }
      return next
    })
  }

  function applyRecSelection() {
    const chosen = [...selectedRecs].map((i) => cityRecs[i])
    if (chosen.length === 0) return
    if (chosen.length === 1) {
      setDestination({ city: chosen[0].name, country: chosen[0].country, lat: chosen[0].lat, lon: chosen[0].lon })
      updateConfig({ destination_mode: 'fixed' })
    } else {
      const [first, ...rest] = chosen
      setDestination({ city: first.name, country: first.country, lat: first.lat, lon: first.lon })
      rest.forEach((c) => addHop({ city: c.name, country: c.country, lat: c.lat, lon: c.lon }))
      updateConfig({ destination_mode: 'fixed' })
    }
  }

  return (
    <section className="space-y-4">
      <h2 className="text-base font-semibold text-[#0F172A]">Origin & Destination *</h2>

      {/* Origin — India only */}
      <GeoInput
        label="🇮🇳 Departure City (India only) *"
        placeholder="e.g. Bengaluru, Mumbai, Delhi"
        value={config.origin.city}
        countrycodes="in"
        countryName="India"
        onSelect={(city, lat, lon) => setOrigin({ ...config.origin, city, lat, lon })}
        onTextChange={(city) => setOrigin({ ...config.origin, city })}
      />

      {/* Destination mode */}
      <div className="flex gap-3 flex-wrap">
        {(['fixed', 'exploring', 'country'] as const).map((mode) => (
          <button
            key={mode}
            onClick={() => updateConfig({ destination_mode: mode as DestinationMode })}
            className={[
              'px-4 py-2 rounded-lg border text-sm font-medium transition-all',
              config.destination_mode === mode
                ? 'bg-[#1E40AF] border-[#1E40AF] text-white'
                : 'bg-white border-slate-300 text-slate-700 hover:border-[#1E40AF]',
            ].join(' ')}
          >
            {mode === 'fixed' ? '📍 Fixed City' : mode === 'exploring' ? '🔍 Explore by Theme' : '🌍 Recommend Cities'}
          </button>
        ))}
      </div>

      {/* Fixed destination */}
      {config.destination_mode === 'fixed' && (
        <div className="space-y-3">
          <GeoInput
            label="🌍 Primary Destination"
            placeholder="e.g. Kuala Lumpur, Malaysia"
            value={config.destination?.city ?? ''}
            onSelect={(city, lat, lon) =>
              setDestination({ city, country: '', lat, lon } satisfies DestinationInput)
            }
            onTextChange={(city) =>
              setDestination(city ? { city, country: '', lat: 0, lon: 0 } : null)
            }
          />

          {/* Multi-hop stops */}
          {config.hops.map((hop, i) => (
            <div key={i} className="flex gap-2 items-start">
              <div className="flex-1">
                <GeoInput
                  label={`🛑 Stop ${i + 1}`}
                  placeholder="e.g. Amsterdam, Netherlands"
                  value={hop.city}
                  onSelect={(city, lat, lon) => {
                    const updated = [...config.hops]
                    updated[i] = { city, country: '', lat, lon }
                    updateConfig({ hops: updated })
                  }}
                  onTextChange={(city) => {
                    const updated = [...config.hops]
                    updated[i] = { ...updated[i], city }
                    updateConfig({ hops: updated })
                  }}
                />
              </div>
              <button
                onClick={() => removeHop(i)}
                className="mt-5 w-8 h-8 rounded-lg border border-red-200 text-red-400 hover:bg-red-50 text-sm flex items-center justify-center shrink-0"
                title="Remove stop"
              >✕</button>
            </div>
          ))}

          {/* Journey breadcrumb */}
          {config.destination && (
            <div className="flex flex-wrap items-center gap-1 text-xs text-slate-500 bg-slate-50 rounded-lg px-3 py-2">
              <span className="font-medium text-slate-700">{config.origin.city || 'Origin'}</span>
              {[config.destination, ...config.hops].map((s, i) => (
                <span key={i} className="flex items-center gap-1">
                  <span>→</span>
                  <span className="font-medium text-[#1E40AF]">{s.city}</span>
                </span>
              ))}
              <span>→ <span className="font-medium text-slate-700">{config.origin.city || 'Origin'}</span></span>
            </div>
          )}

          {/* Add hop button */}
          {config.hops.length < 5 && config.destination && (
            <button
              onClick={() => addHop({ city: '', country: '', lat: 0, lon: 0 })}
              className="flex items-center gap-2 text-sm text-[#1E40AF] hover:text-blue-800 font-medium"
            >
              <span className="w-6 h-6 rounded-full border-2 border-current flex items-center justify-center text-xs font-bold">+</span>
              Add Stop ({config.hops.length}/5)
            </button>
          )}
        </div>
      )}

      {/* Explore by theme */}
      {config.destination_mode === 'exploring' && (
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

      {/* Country → AI city recommendations */}
      {config.destination_mode === 'country' && (
        <div className="space-y-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={countryInput}
              onChange={(e) => setCountryInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleGetCityRecs()}
              placeholder="e.g. Japan, France, Thailand"
              className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1E40AF]"
            />
            <button
              onClick={handleGetCityRecs}
              disabled={!countryInput.trim() || recLoading}
              className="px-4 py-2 rounded-lg bg-[#1E40AF] text-white text-sm font-medium disabled:bg-slate-200 disabled:text-slate-400 transition-all"
            >
              {recLoading ? '⏳' : '✨ Get Recs'}
            </button>
          </div>

          {cityRecs.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs text-slate-500">Select one city (fixed destination) or multiple (multi-hop):</p>
              <div className="grid gap-2">
                {cityRecs.map((city, i) => (
                  <button
                    key={i}
                    onClick={() => toggleRec(i)}
                    className={[
                      'text-left px-3 py-2.5 rounded-lg border text-sm transition-all',
                      selectedRecs.has(i)
                        ? 'bg-blue-50 border-[#1E40AF] text-[#1E40AF]'
                        : 'bg-white border-slate-200 text-slate-700 hover:border-slate-400',
                    ].join(' ')}
                  >
                    <span className="font-medium">{selectedRecs.has(i) ? '✅ ' : ''}{city.name}</span>
                    <span className="text-slate-400 ml-1 text-xs">· {city.country}</span>
                    <p className="text-xs text-slate-500 mt-0.5">{city.reason}</p>
                  </button>
                ))}
              </div>

              {selectedRecs.size > 0 && (
                <button
                  onClick={applyRecSelection}
                  className="w-full py-2 rounded-lg bg-[#1E40AF] text-white text-sm font-semibold hover:bg-blue-800 transition-all"
                >
                  {selectedRecs.size === 1
                    ? `Set ${cityRecs[[...selectedRecs][0]].name} as destination`
                    : `Plan ${selectedRecs.size}-city multi-hop trip`}
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

// ── Reusable geocoded text input ──────────────────────────────────────────────
interface GeoInputProps {
  label: string
  placeholder: string
  value: string
  countrycodes?: string
  countryName?: string
  onSelect: (city: string, lat: number, lon: number) => void
  onTextChange: (city: string) => void
}

function GeoInput({ label, placeholder, value, countrycodes, countryName, onSelect, onTextChange }: GeoInputProps) {
  const [text, setText] = useState(value)
  const [suggestion, setSuggestion] = useState<{ city: string; lat: number; lon: number } | null>(null)
  const [loading, setLoading] = useState(false)
  const [countryError, setCountryError] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => { setText(value) }, [value])

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value
    setText(v)
    onTextChange(v)
    setSuggestion(null)
    setCountryError(false)

    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (v.length < 3) return
    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const result = await geocode(v, countrycodes)
        if (countrycodes && result.country_code !== countrycodes) {
          setCountryError(true)
          return
        }
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
          className={[
            'w-full border rounded-lg px-3 py-2 text-sm focus:outline-none',
            countryError
              ? 'border-red-400 focus:border-red-500'
              : 'border-slate-300 focus:border-[#1E40AF]',
          ].join(' ')}
        />
        {loading && (
          <span className="absolute right-3 top-2.5 w-3 h-3 border-2 border-[#1E40AF] border-t-transparent rounded-full animate-spin" />
        )}
      </div>
      {countryError && (
        <p className="mt-1 text-xs text-red-500">
          ⚠️ Please enter a city in {countryName ?? 'the required country'}.
        </p>
      )}
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

