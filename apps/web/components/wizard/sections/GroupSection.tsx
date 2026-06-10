'use client'

import { useTripConfigStore } from '@/store/tripConfigStore'

function Counter({
  label, value, onChange,
}: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
      <span className="text-sm text-slate-700">{label}</span>
      <div className="flex items-center gap-3">
        <button
          onClick={() => onChange(Math.max(0, value - 1))}
          className="w-7 h-7 rounded-full border border-slate-300 text-slate-600 flex items-center justify-center hover:border-[#1E40AF] text-lg leading-none"
        >
          −
        </button>
        <span className="w-5 text-center text-sm font-medium">{value}</span>
        <button
          onClick={() => onChange(value + 1)}
          className="w-7 h-7 rounded-full border border-slate-300 text-slate-600 flex items-center justify-center hover:border-[#1E40AF] text-lg leading-none"
        >
          +
        </button>
      </div>
    </div>
  )
}

export function GroupSection() {
  const group = useTripConfigStore((s) => s.config.group)
  const updateGroup = useTripConfigStore((s) => s.updateGroup)
  const effectivePace = useTripConfigStore((s) => s.effectivePace)

  const hasYoungKid = group.kids.some((k) => k.age < 5)
  const autoRelaxed = effectivePace() === 'relaxed' && hasYoungKid

  function addKid() {
    updateGroup({ kids: [...group.kids, { age: 5 }] })
  }

  function updateKidAge(idx: number, age: number) {
    const updated = group.kids.map((k, i) => (i === idx ? { age } : k))
    updateGroup({ kids: updated })
  }

  function removeKid(idx: number) {
    updateGroup({ kids: group.kids.filter((_, i) => i !== idx) })
  }

  return (
    <section className="space-y-3">
      <h2 className="text-base font-semibold text-[#0F172A]">Group Composition</h2>
      <div className="bg-slate-50 rounded-lg px-4 py-2">
        <Counter label="Infants (0–2 yrs)" value={group.infants} onChange={(v) => updateGroup({ infants: v })} />
        <Counter label="Adults (8+ yrs)" value={group.adults} onChange={(v) => updateGroup({ adults: v })} />
        <Counter label="Seniors (60+ yrs)" value={group.seniors} onChange={(v) => updateGroup({ seniors: v })} />
        <Counter label="Pets" value={group.pets} onChange={(v) => updateGroup({ pets: v })} />
      </div>

      {/* Kids */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-slate-700">Kids (2–8 yrs)</span>
          <button
            onClick={addKid}
            className="text-xs text-[#1E40AF] hover:underline font-medium"
          >
            + Add child
          </button>
        </div>
        {group.kids.map((kid, idx) => (
          <div key={idx} className="flex items-center gap-3 bg-slate-50 rounded-lg px-4 py-2">
            <span className="text-sm text-slate-600">Child {idx + 1}</span>
            <div className="flex items-center gap-2 ml-auto">
              <span className="text-xs text-slate-500">Age:</span>
              <input
                type="number"
                min={2}
                max={8}
                value={kid.age}
                onChange={(e) => updateKidAge(idx, Number(e.target.value))}
                className="w-14 border border-slate-300 rounded px-2 py-1 text-sm text-center focus:outline-none focus:border-[#1E40AF]"
              />
              <button
                onClick={() => removeKid(idx)}
                className="text-slate-400 hover:text-red-500 ml-1"
              >
                ×
              </button>
            </div>
          </div>
        ))}
        {autoRelaxed && (
          <p className="text-xs text-[#047857] bg-emerald-50 border border-emerald-200 rounded px-3 py-1.5">
            ✓ Pace set to Relaxed — recommended for groups with young children.
          </p>
        )}
      </div>
    </section>
  )
}
