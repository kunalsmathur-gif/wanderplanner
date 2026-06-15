'use client'

import { useItineraryStore } from '@/store/itineraryStore'

const TAG_STYLES: Record<string, string> = {
  instaworthy: 'bg-amber-100 text-amber-700',
  kid_friendly: 'bg-green-100 text-green-700',
  work_block: 'bg-blue-100 text-blue-700',
  training_window: 'bg-purple-100 text-purple-700',
  pet_friendly: 'bg-emerald-100 text-emerald-700',
}

export function ItineraryTimeline() {
  const { days, activeDay, hoveredItemId, setActiveDay, setHoveredItem } = useItineraryStore()
  const day = days[activeDay]

  if (!day) return (
    <div className="flex items-center justify-center h-full text-slate-400 text-sm">
      No itinerary loaded.
    </div>
  )

  return (
    <div className="flex flex-col h-full">
      {/* Day tabs */}
      <div className="flex gap-0 border-b border-slate-200 bg-white overflow-x-auto shrink-0">
        {days.map((d, idx) => (
          <button
            key={d.day_number}
            onClick={() => setActiveDay(idx)}
            className={[
              'px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-all shrink-0',
              idx === activeDay
                ? 'border-[#1E40AF] text-[#1E40AF]'
                : 'border-transparent text-slate-500 hover:text-slate-800',
            ].join(' ')}
          >
            Day {d.day_number}
            <span className="block text-xs font-normal text-slate-400">{d.date}</span>
          </button>
        ))}
      </div>

      {/* Timeline */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        <p className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
          {day.theme}
        </p>

        {day.items.map((item) => (
          <div
            key={item.id}
            onMouseEnter={() => setHoveredItem(item.id)}
            onMouseLeave={() => setHoveredItem(null)}
            className={[
              'bg-white border rounded-lg p-4 cursor-pointer transition-all',
              'hover:border-[#1E40AF]',
              item.id === hoveredItemId ? 'border-[#1E40AF] shadow-md' : 'border-slate-200',
            ].join(' ')}
            style={{ boxShadow: item.id === hoveredItemId ? '0 4px 6px -1px rgb(0 0 0 / 0.08)' : '0 4px 6px -1px rgb(0 0 0 / 0.05)' }}
          >
            <div className="flex items-start gap-3">
              <div className="text-xs text-slate-400 w-20 shrink-0 pt-0.5">
                {item.time_start}<br />→ {item.time_end}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-[#0F172A] text-sm">{item.title}</h3>
                {item.local_name && (
                  <p className="text-xs text-slate-400 mt-0.5">{item.local_name}</p>
                )}
                <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{item.description}</p>
                <div className="flex flex-wrap gap-1 mt-2">
                  {item.tags.map((tag) => (
                    <span
                      key={tag}
                      className={[
                        'text-xs rounded px-1.5 py-0.5 font-medium',
                        TAG_STYLES[tag] ?? 'bg-slate-100 text-slate-600',
                      ].join(' ')}
                    >
                      {tag === 'instaworthy' ? '📸 ' : ''}{tag.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>
                {item.booking_url && (
                  <a
                    href={item.booking_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-[#1E40AF] hover:underline mt-1 inline-block"
                  >
                    Book →
                  </a>
                )}
                {item.youtube_search_query && (
                  <a
                    href={`https://www.youtube.com/results?search_query=${encodeURIComponent(item.youtube_search_query)}&sp=CAMSAhAB`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-red-500 hover:underline mt-1 inline-block ml-3"
                  >
                    ▶ Watch on YouTube
                  </a>
                )}
              </div>
            </div>
          </div>
        ))}

        {day.transit_warnings.map((w, i) => (
          <div key={i} className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2">
            <span className="text-amber-500 shrink-0">⚠</span>
            <p className="text-xs text-amber-700">{w.message}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
