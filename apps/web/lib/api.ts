import axios from 'axios'
import type { TripConfig, ItineraryResponse, ComparisonResponse, DestinationInput, FeasibilityResponse, RecommendCitiesResponse, ChatRefineResponse } from '@/types'

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
  timeout: 25_000,
})

// ── Geocode ───────────────────────────────────────────────────────────────
export async function geocode(query: string, countrycodes?: string) {
  const { data } = await api.get('/api/geocode', {
    params: { q: query, ...(countrycodes ? { countrycodes } : {}) },
  })
  return data as { display_name: string; lat: number; lon: number; country_code: string; is_country: boolean }
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

// ── Chat ──────────────────────────────────────────────────────────────────
export async function sendChatMessage(
  messages: Array<{ role: string; content: string }>,
  tripContext?: Record<string, unknown>,
): Promise<string> {
  const { data } = await api.post('/api/chat', {
    messages,
    trip_context: tripContext ?? null,
  })
  return (data as { reply: string }).reply
}

// ── Chat refine (R13) ────────────────────────────────────────────────────
export async function chatRefine(
  messages: Array<{ role: string; content: string }>,
  tripConfig: TripConfig,
): Promise<ChatRefineResponse> {
  const { data } = await api.post('/api/chat-refine', {
    messages,
    trip_config: tripConfig,
  })
  return data as ChatRefineResponse
}

// ── Recommend cities (R15) ───────────────────────────────────────────────
export async function recommendCities(
  country: string,
  tripConfig: TripConfig,
): Promise<RecommendCitiesResponse> {
  const { data } = await api.post('/api/recommend-cities', {
    country,
    trip_config: tripConfig,
  })
  return data as RecommendCitiesResponse
}

// ── Feasibility check ────────────────────────────────────────────────────
export async function checkFeasibility(tripConfig: TripConfig) {
  const { data } = await api.post('/api/feasibility-check', { trip_config: tripConfig })
  return data as FeasibilityResponse
}

// ── Extract trip from URL / text (Start Anywhere) ────────────────────────
export interface ExtractedTrip {
  destination: string | null
  destination_country: string | null
  duration_days: number | null
  themes: string[]
  budget_inr: number | null
  summary: string
}

export async function extractTrip(input: string): Promise<ExtractedTrip> {
  const { data } = await api.post('/api/extract-trip', { input })
  return data as ExtractedTrip
}

// ── Share trip ───────────────────────────────────────────────────────────
export async function shareTrip(payload: {
  itinerary: object
  trip_config: object
  labels: object
  destination_label: string
}): Promise<{ slug: string; url: string }> {
  const { data } = await api.post('/api/share', payload)
  return data as { slug: string; url: string }
}

export async function getSharedTrip(slug: string): Promise<{
  itinerary: object
  trip_config: object
  labels: object
  destination_label: string
}> {
  const { data } = await api.get(`/api/share/${slug}`)
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

// ── Travel tips (Reddit + web articles fallback) ──────────────────────────
export interface TravelTip {
  title: string
  text_preview: string
  post_url: string
  source: string
  score: number
  thumbnailUrl?: string | null  // YouTube thumbnail URL
}

export async function getTravelTips(destination: string, limit = 6): Promise<TravelTip[]> {
  const { data } = await api.get('/api/travel-tips', {
    params: { destination, limit },
  })
  return (data as { tips: TravelTip[] }).tips
}
export interface RedditPost {
  title: string
  text_preview: string
  post_url: string
  subreddit: string
  score: number
}

export async function getRedditHighlights(destination: string, limit = 5): Promise<RedditPost[]> {
  const { data } = await api.get('/api/reddit-highlights', {
    params: { destination, limit },
  })
  return (data as { posts: RedditPost[] }).posts
}
