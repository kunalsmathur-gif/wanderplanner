'use client'

import { useTripConfigStore } from '@/store/tripConfigStore'

const STYLES = ['Hotel', 'BnB', 'Service Apartment', 'Resort']
const PROPERTIES = [
  { key: 'private_pool', label: 'Private Pool' },
  { key: 'kitchen', label: 'Kitchen' },
  { key: 'wheelchair_accessible', label: 'Wheelchair Accessible' },
  { key: 'pet_friendly', label: 'Pet Friendly' },
] as const

export function AccommodationSection() {
  const acc = useTripConfigStore((s) => s.config.accommodation)
  const updateAccommodation = useTripConfigStore((s) => s.updateAccommodation)

  function toggleStyle(style: string) {
    updateAccommodation({
      style: acc.style.includes(style)
        ? acc.style.filter((s) => s !== style)
        : [...acc.style, style],
    })
  }

  return (
    <section className="space-y-4">
      <h2 className="text-base font-semibold text-[#0F172A]">Accommodations</h2>

      <div>
        <label className="block text-xs text-slate-500 mb-2">Style</label>
        <div className="flex flex-wrap gap-2">
          {STYLES.map((s) => (
            <button
              key={s}
              onClick={() => toggleStyle(s)}
              className={[
                'px-3 py-1.5 rounded-lg border text-sm transition-all',
                acc.style.includes(s)
                  ? 'bg-[#1E40AF] border-[#1E40AF] text-white'
                  : 'bg-white border-slate-300 text-slate-700 hover:border-[#1E40AF]',
              ].join(' ')}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-6">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Min Bedrooms</label>
          <input
            type="number" min={1} max={10}
            value={acc.min_bedrooms}
            onChange={(e) => updateAccommodation({ min_bedrooms: Number(e.target.value) })}
            className="w-20 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1E40AF]"
          />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Bathrooms</label>
          <input
            type="number" min={1} max={10}
            value={acc.bathrooms}
            onChange={(e) => updateAccommodation({ bathrooms: Number(e.target.value) })}
            className="w-20 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1E40AF]"
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-2">
        {PROPERTIES.map(({ key, label }) => (
          <label key={key} className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={acc[key]}
              onChange={(e) => updateAccommodation({ [key]: e.target.checked })}
              className="accent-[#1E40AF] w-4 h-4"
            />
            <span className="text-sm text-slate-700">{label}</span>
          </label>
        ))}
      </div>
    </section>
  )
}
