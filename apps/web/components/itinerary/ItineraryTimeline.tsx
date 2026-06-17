'use client'

import { useEffect, useState } from 'react'
import { useItineraryStore } from '@/store/itineraryStore'
import type { ItineraryItem } from '@/types'

const TAG_STYLES: Record<string, string> = {
  instaworthy: 'bg-amber-100 text-amber-700',
  kid_friendly: 'bg-green-100 text-green-700',
  work_block: 'bg-blue-100 text-blue-700',
  training_window: 'bg-purple-100 text-purple-700',
  pet_friendly: 'bg-emerald-100 text-emerald-700',
}

const thumbnailCache = new Map<string, string | null>()
const videoIdCache = new Map<string, string | null>()

function useThumbnail(query?: string, fallbackVideoId?: string) {
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(() => {
    if (fallbackVideoId) return `https://img.youtube.com/vi/${fallbackVideoId}/mqdefault.jpg`
    return query ? (thumbnailCache.get(query) ?? null) : null
  })
  const [videoId, setVideoId] = useState<string | null>(() => {
    if (fallbackVideoId) return fallbackVideoId
    return query ? (videoIdCache.get(query) ?? null) : null
  })

  useEffect(() => {
    if (fallbackVideoId) {
      setVideoId(fallbackVideoId)
      setThumbnailUrl(`https://img.youtube.com/vi/${fallbackVideoId}/mqdefault.jpg`)
      return
    }

    if (!query) {
      setVideoId(null)
      setThumbnailUrl(null)
      return
    }

    if (thumbnailCache.has(query)) {
      setThumbnailUrl(thumbnailCache.get(query) ?? null)
      setVideoId(videoIdCache.get(query) ?? null)
      return
    }

    let cancelled = false

    fetch(`/api/youtube-thumbnail?q=${encodeURIComponent(query)}`)
      .then((response) => response.json())
      .then((data: { videoId: string | null; thumbnailUrl: string | null }) => {
        thumbnailCache.set(query, data.thumbnailUrl)
        videoIdCache.set(query, data.videoId)

        if (!cancelled) {
          setThumbnailUrl(data.thumbnailUrl)
          setVideoId(data.videoId)
        }
      })
      .catch(() => {
        thumbnailCache.set(query, null)
        videoIdCache.set(query, null)

        if (!cancelled) {
          setThumbnailUrl(null)
          setVideoId(null)
        }
      })

    return () => {
      cancelled = true
    }
  }, [fallbackVideoId, query])

  return { thumbnailUrl, videoId }
}

export function ItineraryTimeline() {
  const { days, activeDay, hoveredItemId, setActiveDay, setHoveredItem } = useItineraryStore()
  const day = days[activeDay]

  if (!day) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-400">
        No itinerary loaded.
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 gap-0 overflow-x-auto border-b border-slate-200 bg-white">
        {days.map((itineraryDay, index) => (
          <button
            key={itineraryDay.day_number}
            onClick={() => setActiveDay(index)}
            className={[
              'shrink-0 whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium transition-all',
              index === activeDay
                ? 'border-[#1E40AF] text-[#1E40AF]'
                : 'border-transparent text-slate-500 hover:text-slate-800',
            ].join(' ')}
            type="button"
          >
            Day {itineraryDay.day_number}
            <span className="block text-xs font-normal text-slate-400">{itineraryDay.date}</span>
          </button>
        ))}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          {day.theme}
        </p>

        {day.items.map((item) => (
          <div
            key={item.id}
            onMouseEnter={() => setHoveredItem(item.id)}
            onMouseLeave={() => setHoveredItem(null)}
            className={[
              'cursor-pointer rounded-lg border bg-white p-4 transition-all hover:border-[#1E40AF]',
              item.id === hoveredItemId ? 'border-[#1E40AF] shadow-md' : 'border-slate-200',
            ].join(' ')}
            style={{ boxShadow: item.id === hoveredItemId ? '0 4px 6px -1px rgb(0 0 0 / 0.08)' : '0 4px 6px -1px rgb(0 0 0 / 0.05)' }}
          >
            <div className="flex items-start gap-3">
              <div className="w-20 shrink-0 pt-0.5 text-xs text-slate-400">
                {item.time_start}<br />→ {item.time_end}
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="text-sm font-semibold text-[#0F172A]">{item.title}</h3>
                {item.local_name && (
                  <p className="mt-0.5 text-xs text-slate-400">{item.local_name}</p>
                )}
                <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">{item.description}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {item.tags.map((tag) => (
                    <span
                      key={tag}
                      className={[
                        'rounded px-1.5 py-0.5 text-xs font-medium',
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
                    className="mt-1 inline-block text-xs text-[#1E40AF] hover:underline"
                  >
                    Book →
                  </a>
                )}
                {(item.youtube_search_query || item.youtube_video_id) && <YouTubeLinkCard item={item} />}
              </div>
            </div>
          </div>
        ))}

        {day.transit_warnings.map((warning, index) => (
          <div key={index} className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2">
            <span className="shrink-0 text-amber-500">⚠</span>
            <p className="text-xs text-amber-700">{warning.message}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function YouTubeLinkCard({ item }: { item: ItineraryItem }) {
  const { thumbnailUrl, videoId } = useThumbnail(item.youtube_search_query, item.youtube_video_id || undefined)

  const href = videoId
    ? `https://youtube.com/watch?v=${videoId}`
    : `https://www.youtube.com/results?search_query=${encodeURIComponent(item.youtube_search_query ?? '')}&sp=CAMSAhAB`

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="mt-2 flex h-[52px] items-center gap-2 overflow-hidden rounded-lg bg-slate-900 transition-opacity hover:opacity-90"
    >
      {thumbnailUrl ? (
        <img
          src={thumbnailUrl}
          alt="Video thumbnail"
          className="h-full w-[92px] shrink-0 object-cover"
        />
      ) : (
        <div className="flex h-full w-[92px] shrink-0 items-center justify-center bg-red-600">
          <svg viewBox="0 0 24 24" fill="white" className="h-8 w-8"><path d="M8 5v14l11-7z" /></svg>
        </div>
      )}
      <div className="min-w-0 flex-1 px-2">
        <p className="line-clamp-2 text-xs font-medium leading-tight text-white">
          {item.youtube_search_query || 'Watch travel guide'}
        </p>
        <p className="mt-0.5 text-xs text-red-400">YouTube →</p>
      </div>
    </a>
  )
}
