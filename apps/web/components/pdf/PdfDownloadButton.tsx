'use client'

import { useState } from 'react'
import { getDayPhotos, type DayPhoto } from '@/lib/api'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import type { ItineraryDay } from '@/types'

/**
 * Ceiling on a single `.toBlob()` attempt. Generous — a long illustrated
 * itinerary genuinely takes seconds to lay out — but finite, because the
 * alternative to finite is a button that never comes back.
 */
const RENDER_TIMEOUT_MS = 20_000

/** Reject if `promise` has not settled within `ms`.
 *
 * ⚠️ The loser of the race is not cancellable: `@react-pdf` exposes no abort,
 * so a hung render keeps running in the background until its image fetch
 * finally gives up. This bounds what the *user* waits for, not what the tab
 * does. Acceptable here — the retry renders without images, so the abandoned
 * attempt is not competing for the same resource. */
export function withDeadline<T>(promise: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout>
  return Promise.race([
    promise,
    new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error('PDF render timed out')), ms)
    }),
  ]).finally(() => clearTimeout(timer)) as Promise<T>
}

/**
 * Attach one hero photo per day, at download time.
 *
 * The query must stay identical to the one generation used to build
 * ("{city or country} {day theme}") — `services/pexels.py` caches per query
 * string, so drifting from it silently doubles Pexels calls for the same
 * photos. `destinationLabel` mirrors the backend's old fallback chain.
 *
 * ⚠️ Every failure path returns the days untouched rather than propagating.
 * This was best-effort when it lived on the generation path and it stays
 * best-effort here: an unavailable photo must cost the user their images,
 * never their PDF. `photosAttached` tells the caller whether a retry without
 * images is even worth attempting.
 */
async function withDayPhotos(
  days: ItineraryDay[],
  destinationLabel: string,
): Promise<{ days: ItineraryDay[]; photosAttached: boolean }> {
  if (!days.length) return { days, photosAttached: false }

  let photos: DayPhoto[]
  try {
    photos = await getDayPhotos(days.map((d) => `${destinationLabel} ${d.theme}`))
  } catch {
    // Pexels down, our endpoint 500ing, rate-limited (429), session expired
    // (401), offline, or past PHOTO_FETCH_TIMEOUT_MS — all the same outcome.
    return { days, photosAttached: false }
  }

  // A short batch can come back if the request was truncated; index past the
  // end yields undefined, which the `!photo?.url` guard already treats as
  // "no photo for this day".
  let photosAttached = false
  const illustrated = days.map((day, i) => {
    const photo = photos[i]
    if (!photo?.url) return day
    photosAttached = true
    return {
      ...day,
      image_url: photo.url,
      image_photographer: photo.photographer,
      image_photographer_url: photo.photographer_url,
    }
  })

  return { days: illustrated, photosAttached }
}

export function PdfDownloadButton() {
  const days = useItineraryStore((s) => s.days)
  const expenseBreakdown = useItineraryStore((s) => s.expenseBreakdown)
  const config = useTripConfigStore((s) => s.config)
  const [generating, setGenerating] = useState(false)
  const [failed, setFailed] = useState(false)

  const fileName = config.destination?.city
    ? `${config.destination.city.replace(/\s+/g, '_')}_WanderPlanner.pdf`
    : 'WanderPlanner_Itinerary.pdf'

  // Mirrors the fallback chain the backend used when it built these queries
  // during generation, so the cache key is unchanged.
  const destinationLabel = config.destination?.city || config.destination_country || 'travel'

  // The document is rendered to a blob only when the user actually asks for
  // it — @react-pdf's <PDFDownloadLink> renders on mount, which cost a full
  // PDF build on every dashboard load (audit §2.3). The renderer itself is
  // imported on demand too, keeping it out of the dashboard bundle.
  async function handleDownload() {
    if (generating) return
    setGenerating(true)
    setFailed(false)
    try {
      const [{ pdf }, { ItineraryDocument }, photoResult] = await Promise.all([
        import('@react-pdf/renderer'),
        import('./ItineraryDocument'),
        withDayPhotos(days, destinationLabel),
      ])

      const render = (source: typeof days) =>
        pdf(
          <ItineraryDocument days={source} config={config} expenseBreakdown={expenseBreakdown} />,
        ).toBlob()

      let blob: Blob
      try {
        // 🔴 The photo can pass the fetch above and still sink the download.
        // @react-pdf resolves every `<Image src>` over the network *at render
        // time*, and **it applies no timeout of its own**. A Pexels CDN URL
        // that 404s or serves a format the renderer rejects throws out of
        // `.toBlob()`; one that simply hangs is worse — the promise never
        // settles, so `catch` never runs, `finally` never runs, and the button
        // sits on "Preparing PDF…" forever with no error and no way out but a
        // reload. That is the reported symptom, and a plain try/catch cannot
        // see it. Racing a deadline turns the hang into a rejection, which the
        // existing image-free retry below already knows how to handle.
        blob = await withDeadline(render(photoResult.days), RENDER_TIMEOUT_MS)
      } catch (err) {
        // Retry once with the photos stripped — but only when photos were
        // actually attached. Otherwise this is an unrelated render failure and
        // re-running it would fail identically, doubling the user's wait
        // before the error appears.
        if (!photoResult.photosAttached) throw err
        blob = await withDeadline(render(days), RENDER_TIMEOUT_MS)
      }

      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = fileName
      anchor.click()
      URL.revokeObjectURL(url)
    } catch {
      setFailed(true)
    } finally {
      setGenerating(false)
    }
  }

  if (!days.length) return (
    <button
      disabled
      className="btn btn-primary h-11 w-full cursor-not-allowed text-sm opacity-45"
    >
      ⬇️ Download Itinerary PDF
    </button>
  )

  return (
    <div className="space-y-1">
      <button
        onClick={handleDownload}
        disabled={generating}
        className={[
          'btn btn-primary h-11 w-full text-sm shadow-md shadow-[var(--_primary)]/20',
          generating ? 'cursor-not-allowed' : '',
        ].join(' ')}
      >
        {generating ? 'Preparing PDF…' : '⬇️ Download Itinerary PDF'}
      </button>
      {failed && (
        <p className="text-xs text-[var(--_destructive)]">
          Could not generate the PDF — please try again.
        </p>
      )}
    </div>
  )
}
