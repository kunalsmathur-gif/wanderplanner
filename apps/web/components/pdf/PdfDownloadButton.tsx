'use client'

import { PDFDownloadLink } from '@react-pdf/renderer'
import { ItineraryDocument } from './ItineraryDocument'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'

export function PdfDownloadButton() {
  const days = useItineraryStore((s) => s.days)
  const expenseBreakdown = useItineraryStore((s) => s.expenseBreakdown)
  const config = useTripConfigStore((s) => s.config)

  const fileName = config.destination?.city
    ? `${config.destination.city.replace(/\s+/g, '_')}_WanderPlanner.pdf`
    : 'WanderPlanner_Itinerary.pdf'

  if (!days.length) return (
    <button
      disabled
      className="w-full h-9 rounded-lg text-xs font-semibold bg-[var(--_muted)] text-[var(--_muted-fg)] cursor-not-allowed"
    >
      ⬇️ Download PDF
    </button>
  )

  return (
    <PDFDownloadLink
      document={
        <ItineraryDocument
          days={days}
          config={config}
          expenseBreakdown={expenseBreakdown}
        />
      }
      fileName={fileName}
      className="block"
    >
      {({ loading }) => (
        <button
          disabled={loading}
          className={[
            'w-full h-9 rounded-lg text-xs font-semibold transition-all',
            loading
              ? 'bg-[var(--_muted)] text-[var(--_muted-fg)] cursor-not-allowed'
              : 'bg-[var(--_muted)] text-[var(--_fg)] hover:bg-[var(--_border)]/40 border border-[var(--_border)]',
          ].join(' ')}
        >
          {loading ? 'Preparing PDF…' : '⬇️ Download PDF'}
        </button>
      )}
    </PDFDownloadLink>
  )
}
