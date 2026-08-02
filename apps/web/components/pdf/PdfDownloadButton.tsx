'use client'

import { useState } from 'react'
import { getDayPhotos, type DayPhoto } from '@/lib/api'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import type { ItineraryDay } from '@/types'

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
        blob = await render(photoResult.days)
      } catch (err) {
        // 🔴 The photo can pass the fetch above and still sink the download.
        // @react-pdf resolves every `<Image src>` over the network *at render
        // time*, so a Pexels CDN URL that 404s, hangs, or serves a format the
        // renderer rejects throws out of `.toBlob()` and takes the whole
        // document with it — the user loses the PDF over a decoration.
        // Retry once with the photos stripped. Only when photos were actually
        // attached: otherwise this is an unrelated render failure and
        // re-running it would just fail twice and double the wait.
        if (!photoResult.photosAttached) throw err
        blob = await render(days)
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
