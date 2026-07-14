'use client'

import { useItineraryStore } from '@/store/itineraryStore'
import { useAppStore } from '@/store/appStore'
import { PolaroidCard } from '@/components/itinerary/PolaroidCard'
import type { ItineraryItem } from '@/types'
import { useEffect, useState } from 'react'
import { isSafeExternalUrl } from '@/lib/url-safety'
import { formatDayDate } from '@/lib/format'
import { logClientEvent } from '@/lib/analyticsBeacon'

const thumbnailCache = new Map<string, string | null>()
const videoIdCache   = new Map<string, string | null>()

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
    if (!query) { setVideoId(null); setThumbnailUrl(null); return }
    // Only trust a cached HIT — a cached miss is never stored (see below),
    // so a query that failed once (network blip, transient YouTube block)
    // gets retried on next mount instead of being stuck blank forever.
    if (thumbnailCache.has(query)) {
      setThumbnailUrl(thumbnailCache.get(query) ?? null)
      setVideoId(videoIdCache.get(query) ?? null)
      return
    }
    let cancelled = false

    // Retry with short backoff — the lookup is a live YouTube scrape and
    // fails transiently fairly often (confirmed: the same query can fail
    // then succeed seconds later), so a few retries clear up the vast
    // majority of these without any user action.
    async function fetchWithRetry(): Promise<{ videoId: string | null; thumbnailUrl: string | null }> {
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const r = await fetch(`/api/youtube-thumbnail?q=${encodeURIComponent(query!)}`)
          const d = await r.json()
          logClientEvent('youtube_thumbnail_call', { attempt, found: Boolean(d.videoId) })
          if (d.videoId) return d
        } catch {
          logClientEvent('youtube_thumbnail_failed', { attempt })
        }
        if (attempt < 2) await new Promise((res) => setTimeout(res, 500 * (attempt + 1)))
      }
      return { videoId: null, thumbnailUrl: null }
    }

    fetchWithRetry().then((d) => {
      // Only cache genuine hits — leave misses uncached so future mounts
      // (or navigating back to this day) get another chance.
      if (d.videoId) {
        thumbnailCache.set(query, d.thumbnailUrl)
        videoIdCache.set(query, d.videoId)
      }
      if (!cancelled) { setThumbnailUrl(d.thumbnailUrl); setVideoId(d.videoId) }
    })
    return () => { cancelled = true }
  }, [fallbackVideoId, query])

  return { thumbnailUrl, videoId }
}

function ActivityCard({ item, isActive, onHover, onSelect }: {
  item: ItineraryItem
  isActive: boolean
  onHover: (id: string | null) => void
  onSelect: (id: string) => void
}) {
  const { thumbnailUrl, videoId } = useThumbnail(
    item.youtube_search_query,
    item.youtube_video_id || undefined,
  )

  const videoHref = videoId
    ? `https://youtube.com/watch?v=${videoId}`
    : item.youtube_search_query
      ? `https://www.youtube.com/results?search_query=${encodeURIComponent(item.youtube_search_query)}&sp=CAMSAhAB`
      : null

  // Pick category badge from first tag
  const category = item.tags[0]?.replace(/_/g, ' ') ?? undefined

  return (
    <div
      onMouseEnter={() => onHover(item.id)}
      onMouseLeave={() => onHover(null)}
      onClick={() => onSelect(item.id)}
      role="button"
      tabIndex={0}
      aria-label={`Show ${item.title} on the map`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(item.id) }
      }}
    >
      <PolaroidCard
        time={`${item.time_start} → ${item.time_end}`}
        title={item.title}
        description={item.local_name ? `${item.local_name} · ${item.description}` : item.description}
        category={category}
        imageSrc={thumbnailUrl}
        videoHref={videoHref}
        isActive={isActive}
      />
      {/* Extra tags row */}
      {item.tags.length > 1 && (
        <div className="-mt-1 mb-2 flex flex-wrap gap-1 px-1">
          {item.tags.slice(1).map((tag) => (
            <span
              key={tag}
              className={
                tag === 'hidden_gem'
                  ? 'rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium text-violet-700 dark:bg-violet-900 dark:text-violet-300'
                  : tag === 'pinned'
                  ? 'rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 dark:bg-amber-900 dark:text-amber-300'
                  : 'rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-700 dark:text-slate-400'
              }
            >
              {tag === 'instaworthy' ? '📸 ' : tag === 'hidden_gem' ? '💎 ' : tag === 'pinned' ? '📌 ' : ''}{tag.replace(/_/g, ' ')}
            </span>
          ))}
          {isSafeExternalUrl(item.booking_url) && (
            <a
              href={item.booking_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="rounded bg-[var(--_primary)]/10 px-1.5 py-0.5 text-[10px] font-medium text-[var(--_primary)] hover:underline"
            >
              Book →
            </a>
          )}
        </div>
      )}
    </div>
  )
}

export function ItineraryTimeline() {
  const { days, activeDay, hoveredItemId, setActiveDay, setHoveredItem } = useItineraryStore()
  const setMobileTab = useAppStore((state) => state.setMobileTab)
  const day = days[activeDay]

  // Selecting an activity (tap/click/Enter) both highlights its marker on
  // the map (existing hover-highlight mechanism, reused as "selected") and
  // — critically for mobile, where itinerary/map are separate tabs and
  // touch has no hover state — jumps straight to the Map & Tips tab instead
  // of leaving the user to find it manually via the bottom nav.
  function handleSelectItem(id: string) {
    setHoveredItem(id)
    setMobileTab('map')
  }

  if (!day) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-400">
        No itinerary loaded.
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Day tabs */}
      <div className="flex shrink-0 gap-0 overflow-x-auto border-b border-[var(--_border)] bg-[var(--_card)]">
        {days.map((itineraryDay, index) => (
          <button
            key={itineraryDay.day_number}
            onClick={() => setActiveDay(index)}
            className={[
              'shrink-0 whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium transition-all',
              index === activeDay
                ? 'border-[var(--_primary)] text-[var(--_primary)]'
                : 'border-transparent text-[var(--_muted-fg)] hover:text-[var(--_fg)]',
            ].join(' ')}
            type="button"
          >
            Day {itineraryDay.day_number}
            <span className="block text-xs font-normal text-[var(--_muted-fg)]">{formatDayDate(itineraryDay.date)}</span>
          </button>
        ))}
      </div>

      {/* Activity cards */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-[var(--_muted-fg)]">
          {day.theme}
        </p>

        <div className="space-y-3">
          {day.items.map((item) => (
            <ActivityCard
              key={item.id}
              item={item}
              isActive={item.id === hoveredItemId}
              onHover={setHoveredItem}
              onSelect={handleSelectItem}
            />
          ))}
        </div>

        {day.transit_warnings.map((warning, index) => (
          <div key={index} className="mt-2 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 dark:border-amber-800/40 dark:bg-amber-950/30">
            <span className="shrink-0 text-amber-500">⚠</span>
            <p className="text-xs text-amber-700 dark:text-amber-400">{warning.message}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

