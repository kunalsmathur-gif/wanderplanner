'use client'

import { useTripConfigStore } from '@/store/tripConfigStore'

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

      {/* Origin */}
      <div>
        <label className="block text-xs text-slate-500 mb-1">Origin city / airport *</label>
        <input
          type="text"
          placeholder="e.g. Bangalore, BLR"
          value={config.origin.city}
          onChange={(e) => setOrigin({ ...config.origin, city: e.target.value })}
          className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1E40AF]"
        />
      </div>

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
        <input
          type="text"
          placeholder="e.g. Kuala Lumpur, Malaysia"
          value={config.destination?.city ?? ''}
          onChange={(e) =>
            setDestination(
              e.target.value
                ? { city: e.target.value, country: '', lat: 0, lon: 0 }
                : null,
            )
          }
          className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1E40AF]"
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
