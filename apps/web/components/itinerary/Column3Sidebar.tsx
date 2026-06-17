'use client'

import { useEffect, useState } from 'react'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useWizardChatStore } from '@/store/wizardChatStore'
import { getTravelTips, type TravelTip } from '@/lib/api'
import { MapWrapper } from '@/components/map/MapWrapper'
import { BestTimeWidget } from '@/components/dashboard/BestTimeWidget'

export function Column3Sidebar() {
  const days = useItineraryStore((state) => state.days)
  const activeDay = useItineraryStore((state) => state.activeDay)
  const collectedLabels = useWizardChatStore((state) => state.collectedLabels)
  const configDestination = useTripConfigStore((state) => state.config.destination?.city ?? '')
  const destination = collectedLabels.destination ?? configDestination
  const [tips, setTips] = useState<TravelTip[]>([])
  const [loadingTips, setLoadingTips] = useState(false)

  const day = days[activeDay]

  useEffect(() => {
    let cancelled = false

    if (!destination) {
      setTips([])
      setLoadingTips(false)
      return
    }

    setLoadingTips(true)

    getTravelTips(destination)
      .then(async (data) => {
        if (cancelled) return
        
        // Fetch YouTube thumbnails for each tip
        const tipsWithThumbnails = await Promise.all(
          data.map(async (tip) => {
            try {
              const searchQuery = `${destination} ${tip.title.slice(0, 50)}`
              const res = await fetch(`/api/youtube-thumbnail?q=${encodeURIComponent(searchQuery)}`)
              const { thumbnailUrl } = await res.json()
              return { ...tip, thumbnailUrl }
            } catch {
              return { ...tip, thumbnailUrl: null }
            }
          })
        )
        
        if (!cancelled) setTips(tipsWithThumbnails)
      })
      .catch(() => { if (!cancelled) setTips([]) })
      .finally(() => { if (!cancelled) setLoadingTips(false) })

    return () => { cancelled = true }
  }, [destination])

  return (
    <div className="space-y-4 p-4">
      <MapWrapper />

      {destination && (
        <div className="border-t border-slate-100 pt-2">
          <BestTimeWidget destination={destination} />
        </div>
      )}

      <div>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          🌐 Travel Tips &amp; Community
        </h4>

        {!destination ? (
          <p className="text-xs text-slate-400">No destination selected.</p>
        ) : loadingTips ? (
          <div className="space-y-2">
            <TipSkeletonCard />
            <TipSkeletonCard />
          </div>
        ) : tips.length === 0 ? (
          <p className="text-xs text-slate-500">No tips found for this destination yet.</p>
        ) : (
          <div className="space-y-2">
            {tips.map((tip, idx) => (
              <a
                key={`${tip.post_url}-${idx}`}
                href={tip.post_url}
                target="_blank"
                rel="noopener noreferrer"
                className="block rounded-xl border border-slate-200 bg-white transition-colors hover:border-[#1E40AF] overflow-hidden"
              >
                {tip.thumbnailUrl && (
                  <img
                    src={tip.thumbnailUrl}
                    alt={tip.title}
                    className="w-full h-32 object-cover"
                    loading="lazy"
                  />
                )}
                <div className="p-3">
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-blue-600">
                      {tip.source}
                    </span>
                    {tip.score > 0 && (
                      <span className="text-[11px] font-medium text-slate-400">⬆ {tip.score}</span>
                    )}
                  </div>
                  <p className="line-clamp-2 text-sm font-semibold text-slate-800">{tip.title}</p>
                  {tip.text_preview && (
                    <p className="mt-1 line-clamp-3 text-xs text-slate-500">{tip.text_preview}</p>
                  )}
                </div>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function TipSkeletonCard() {
  return (
    <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-3">
      <div className="h-4 w-20 animate-pulse rounded-full bg-slate-100" />
      <div className="h-4 w-full animate-pulse rounded bg-slate-100" />
      <div className="h-4 w-4/5 animate-pulse rounded bg-slate-100" />
      <div className="h-3 w-full animate-pulse rounded bg-slate-100" />
    </div>
  )
}

