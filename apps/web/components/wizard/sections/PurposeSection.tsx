'use client'

import { useTripConfigStore } from '@/store/tripConfigStore'

const PURPOSES = [
  { id: 'chill', label: '😎 Chill Out' },
  { id: 'explore', label: '🗺️ Explore' },
  { id: 'family_reunion', label: '👨‍👩‍👧 Family Reunion' },
  { id: 'friends', label: '👫 Friends Get-Together' },
  { id: 'special_occasion', label: '🎉 Special Occasion' },
]

export function PurposeSection() {
  const purpose = useTripConfigStore((s) => s.config.purpose)
  const updateConfig = useTripConfigStore((s) => s.updateConfig)

  return (
    <section className="space-y-3">
      <h2 className="text-base font-semibold text-[#0F172A]">Trip Purpose *</h2>
      <div className="flex flex-wrap gap-2">
        {PURPOSES.map((p) => (
          <button
            key={p.id}
            onClick={() => updateConfig({ purpose: p.id })}
            className={[
              'px-4 py-2 rounded-lg border text-sm font-medium transition-all',
              purpose === p.id
                ? 'bg-[#1E40AF] border-[#1E40AF] text-white'
                : 'bg-white border-slate-300 text-slate-700 hover:border-[#1E40AF]',
            ].join(' ')}
          >
            {p.label}
          </button>
        ))}
      </div>
    </section>
  )
}
