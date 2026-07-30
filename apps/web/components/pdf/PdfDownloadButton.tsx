'use client'

import { useState } from 'react'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'

export function PdfDownloadButton() {
  const days = useItineraryStore((s) => s.days)
  const expenseBreakdown = useItineraryStore((s) => s.expenseBreakdown)
  const config = useTripConfigStore((s) => s.config)
  const [generating, setGenerating] = useState(false)
  const [failed, setFailed] = useState(false)

  const fileName = config.destination?.city
    ? `${config.destination.city.replace(/\s+/g, '_')}_WanderPlanner.pdf`
    : 'WanderPlanner_Itinerary.pdf'

  // The document is rendered to a blob only when the user actually asks for
  // it — @react-pdf's <PDFDownloadLink> renders on mount, which cost a full
  // PDF build on every dashboard load (audit §2.3). The renderer itself is
  // imported on demand too, keeping it out of the dashboard bundle.
  async function handleDownload() {
    if (generating) return
    setGenerating(true)
    setFailed(false)
    try {
      const [{ pdf }, { ItineraryDocument }] = await Promise.all([
        import('@react-pdf/renderer'),
        import('./ItineraryDocument'),
      ])
      const blob = await pdf(
        <ItineraryDocument days={days} config={config} expenseBreakdown={expenseBreakdown} />,
      ).toBlob()
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
