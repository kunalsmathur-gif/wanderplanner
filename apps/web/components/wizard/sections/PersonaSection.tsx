'use client'

import { useTripConfigStore } from '@/store/tripConfigStore'

const PERSONAS = [
  { id: 'group_coordinator', label: '👥 Group Coordinator' },
  { id: 'aesthetic_explorer', label: '📸 Aesthetic Explorer' },
  { id: 'pet_parent', label: '🐾 Pet Parent' },
  { id: 'retired_traveler', label: '🧓 Retired Traveler' },
  { id: 'sports_fitness', label: '🏃 Sports & Fitness' },
  { id: 'digital_nomad', label: '💻 Digital Nomad' },
]

export function PersonaSection() {
  const personas = useTripConfigStore((s) => s.config.personas)
  const updateConfig = useTripConfigStore((s) => s.updateConfig)

  function toggle(id: string) {
    updateConfig({
      personas: personas.includes(id)
        ? personas.filter((p) => p !== id)
        : [...personas, id],
    })
  }

  return (
    <section className="space-y-3">
      <h2 className="text-base font-semibold text-[#0F172A]">
        Traveler Personas
        <span className="ml-2 text-xs font-normal text-slate-500">Select all that apply</span>
      </h2>
      <div className="flex flex-wrap gap-2">
        {PERSONAS.map((p) => {
          const selected = personas.includes(p.id)
          return (
            <button
              key={p.id}
              onClick={() => toggle(p.id)}
              className={[
                'px-4 py-2 rounded-lg border text-sm font-medium transition-all flex items-center gap-1',
                selected
                  ? 'bg-[#1E40AF] border-[#1E40AF] text-white'
                  : 'bg-white border-slate-300 text-slate-700 hover:border-[#1E40AF]',
              ].join(' ')}
            >
              {selected && <span className="text-xs">✓</span>}
              {p.label}
            </button>
          )
        })}
      </div>
    </section>
  )
}
