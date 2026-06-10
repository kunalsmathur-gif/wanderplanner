'use client'

import { useItineraryStore } from '@/store/itineraryStore'
import { MapWrapper } from '@/components/map/MapWrapper'

export function Column3Sidebar() {
  const days = useItineraryStore((s) => s.days)
  const activeDay = useItineraryStore((s) => s.activeDay)
  const day = days[activeDay]

  const youtubeId = day?.items.find((i) => i.youtube_video_id)?.youtube_video_id

  return (
    <div className="p-4 space-y-4">
      {/* Interactive map — updates on timeline hover */}
      <MapWrapper />

      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
        📺 Social &amp; Media
      </h3>

      {youtubeId ? (
        <div className="rounded-lg overflow-hidden border border-slate-200">
          <iframe
            src={`https://www.youtube.com/embed/${youtubeId}`}
            title="Travel guide"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            className="w-full aspect-video"
          />
        </div>
      ) : (
        <div className="bg-slate-100 rounded-lg aspect-video flex items-center justify-center text-slate-400 text-sm">
          No video available
        </div>
      )}

      <div>
        <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
          📑 Reddit Highlights
        </h4>
        {day ? (
          <div className="space-y-2">
            <p className="text-xs text-slate-500 italic">
              Real traveler tips for {day.theme.toLowerCase()} will appear here once social data is indexed for this destination.
            </p>
          </div>
        ) : (
          <p className="text-xs text-slate-400">No destination selected.</p>
        )}
      </div>
    </div>
  )
}
