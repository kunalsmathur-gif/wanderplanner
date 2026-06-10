'use client'

import { PDFDownloadLink } from '@react-pdf/renderer'
import { ItineraryDocument } from './ItineraryDocument'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'

export function PdfDownloadButton() {
  const days = useItineraryStore((s) => s.days)
  const config = useTripConfigStore((s) => s.config)

  const fileName = config.destination?.city
    ? `${config.destination.city.replace(/\s+/g, '_')}_WanderPlan.pdf`
    : 'WanderPlan_Itinerary.pdf'

  if (!days.length) return (
    <button
      disabled
      className="w-full h-9 rounded-lg text-xs font-semibold bg-slate-100 text-slate-400 cursor-not-allowed"
    >
      ⬇️ Download PDF
    </button>
  )

  return (
    <PDFDownloadLink
      document={<ItineraryDocument days={days} config={config} />}
      fileName={fileName}
      className="block"
    >
      {({ loading }) => (
        <button
          disabled={loading}
          className={[
            'w-full h-9 rounded-lg text-xs font-semibold transition-all',
            loading
              ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
              : 'bg-slate-100 text-slate-700 hover:bg-slate-200 border border-slate-200',
          ].join(' ')}
        >
          {loading ? 'Preparing PDF…' : '⬇️ Download PDF'}
        </button>
      )}
    </PDFDownloadLink>
  )
}
