import { ImageResponse } from 'next/og'
import { getSharedTrip } from '@/lib/sharedTrip'

export const alt = 'Wanderplanner shared trip'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const data = await getSharedTrip(slug)

  const destination = data?.destination_label || 'A personalised trip'
  const duration = data?.labels?.duration

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'flex-start',
          background: 'linear-gradient(135deg, #0EA5E9 0%, #0369A1 100%)',
          padding: '80px',
          color: 'white',
        }}
      >
        <div style={{ display: 'flex', fontSize: 32, fontWeight: 700, opacity: 0.85 }}>Wanderplanner</div>
        <div style={{ display: 'flex', fontSize: 64, fontWeight: 900, marginTop: 24, maxWidth: 1000 }}>
          {destination}
        </div>
        {duration && (
          <div style={{ display: 'flex', fontSize: 36, marginTop: 16, opacity: 0.9 }}>{duration}</div>
        )}
        <div style={{ display: 'flex', fontSize: 28, marginTop: 40, opacity: 0.8 }}>
          AI-planned day-by-day itinerary →
        </div>
      </div>
    ),
    { ...size },
  )
}
