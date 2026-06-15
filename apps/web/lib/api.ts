import axios from 'axios'
import type { TripConfig, ItineraryResponse, ComparisonResponse, DestinationInput } from '@/types'

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
  timeout: 25_000,
})

// ── Geocode ───────────────────────────────────────────────────────────────
export async function geocode(query: string, countrycodes?: string) {
  const { data } = await api.get('/api/geocode', {
    params: { q: query, ...(countrycodes ? { countrycodes } : {}) },
  })
  return data as { display_name: string; lat: number; lon: number; country_code: string }
}

// ── Search ────────────────────────────────────────────────────────────────
export async function search(query: string, destination: string, limit = 10) {
  const { data } = await api.get('/api/search', {
    params: { q: query, destination, limit },
  })
  return data
}

// ── Best time ─────────────────────────────────────────────────────────────
export async function getBestTime(destination: string) {
  const { data } = await api.get(`/api/best-time/${encodeURIComponent(destination)}`)
  return data
}

// ── Comparison ────────────────────────────────────────────────────────────
export async function compareDestinations(
  destinations: DestinationInput[],
  tripConfig: TripConfig,
): Promise<ComparisonResponse> {
  const { data } = await api.post('/api/compare-destinations', {
    destinations,
    trip_config: tripConfig,
  })
  return data
}

// ── Itinerary (streaming SSE) ─────────────────────────────────────────────
export function streamItinerary(
  tripConfig: TripConfig,
  onStatus: (msg: string, step: number, total: number) => void,
  onData: (result: ItineraryResponse) => void,
  onError: (code: string, message: string, retryable: boolean) => void,
): () => void {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

  const controller = new AbortController()

  fetch(`${baseUrl}/api/generate-itinerary`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trip_config: tripConfig }),
    signal: controller.signal,
  })
    .then(async (res) => {
      const reader = res.body?.getReader()
      if (!reader) return
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const parts = buffer.split('\n\n')
        buffer = parts.pop() ?? ''

        for (const part of parts) {
          const eventMatch = part.match(/^event: (\w+)/)
          const dataMatch = part.match(/^data: (.+)$/m)
          if (!eventMatch || !dataMatch) continue

          const event = eventMatch[1]
          const payload = JSON.parse(dataMatch[1])

          if (event === 'status') {
            onStatus(payload.message, payload.step, payload.total_steps)
          } else if (event === 'data') {
            onData(payload)
          } else if (event === 'error') {
            onError(payload.code, payload.message, payload.retryable)
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError('NETWORK_ERROR', 'Connection failed. Please try again.', true)
      }
    })

  return () => controller.abort()
}
