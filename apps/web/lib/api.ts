import axios from 'axios'
import type { TripConfig, ItineraryResponse, ComparisonResponse, DestinationInput, FeasibilityResponse, RecommendCitiesResponse, ChatRefineResponse } from '@/types'

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
  timeout: 25_000,
  // The itinerary-generation endpoint now requires an authenticated session
  // cookie (see /api/generate-itinerary auth gate) — credentials must be
  // sent even though the frontend/backend are on different origins.
  withCredentials: true,
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

// ── Wizard chat (LLM Anya wizard) ────────────────────────────────────────
export interface WizardChatResponse {
  reply: string
  chips: string[]
  config_patch: Partial<TripConfig>
  ready_to_generate: boolean
  summary: string | null
  // True when `chips` is a multi-value field (e.g. travel themes) the user
  // should be able to pick several of before continuing. Computed
  // deterministically server-side — do not re-derive this on the frontend.
  multi_select: boolean
}

export async function wizardChat(
  messages: Array<{ role: string; content: string; config_patch?: Record<string, unknown> }>,
  partialConfig: Partial<TripConfig>,
  preloadedDestination?: string,
): Promise<WizardChatResponse> {
  const { data } = await api.post(
    '/api/wizard-chat',
    {
      messages,
      partial_config: partialConfig,
      preloaded_destination: preloadedDestination ?? null,
    },
    // Longer timeout than the shared default: the backend retries up to 3x
    // on transient Gemini errors AND on JSON-validity failures, and observed
    // real-world latency for that worst case (5s + 7s + 13s+) can land right
    // at or past the default 25s, surfacing as a spurious "Connection error"
    // even though the backend eventually succeeds.
    { timeout: 45_000 },
  )
  return data as WizardChatResponse
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
  // Same rationale as wizardChat: this endpoint retries up to 3x on Gemini
  // transient errors / JSON-validity failures, which can exceed the shared
  // 25s default in the worst case.
  const { data } = await api.post('/api/extract-trip', { input }, { timeout: 45_000 })
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

// ── Agent leads ──────────────────────────────────────────────────────────
export async function createAgentLead(payload: {
  email: string
  destination: string
  trip_config_summary: Record<string, unknown>
  custom_notes?: string | null
  itinerary_html?: string | null
  pdf_base64?: string | null
}): Promise<{ id: string }> {
  const { data } = await api.post('/api/agent-leads', payload)
  return data as { id: string }
}

// ── Itinerary feedback ───────────────────────────────────────────────────
export type FeedbackScope = 'itinerary' | 'day' | 'place'
export type FeedbackSentiment = 'missed_the_mark' | 'thumbs_up' | 'thumbs_down'

export interface ItineraryFeedbackPayload {
  trip_config_snapshot: Record<string, unknown>
  scope: FeedbackScope
  day_index?: number
  place_ref?: string
  sentiment: FeedbackSentiment
  note?: string
}

export interface ItineraryFeedbackResult {
  id: string
  scope: FeedbackScope
  day_index: number | null
  place_ref: string | null
  sentiment: FeedbackSentiment
  note: string | null
  created_at: string
}

export async function createItineraryFeedback(
  payload: ItineraryFeedbackPayload,
): Promise<ItineraryFeedbackResult> {
  const { data } = await api.post('/api/itinerary-feedback', payload)
  return data as ItineraryFeedbackResult
}

export async function updateItineraryFeedback(
  id: string,
  sentiment: FeedbackSentiment,
): Promise<ItineraryFeedbackResult> {
  const { data } = await api.patch(`/api/itinerary-feedback/${id}`, { sentiment })
  return data as ItineraryFeedbackResult
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

  async function attempt(alreadyRetriedAfterRefresh: boolean): Promise<void> {
    const res = await fetch(`${baseUrl}/api/generate-itinerary`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trip_config: tripConfig }),
      signal: controller.signal,
      // Required to send the httpOnly session cookie — generation now
      // requires authentication (see /api/generate-itinerary auth gate).
      credentials: 'include',
    })

    // The 15-minute access-token cookie may have expired mid-conversation
    // even though the user is genuinely still signed in — try one silent
    // refresh via the longer-lived refresh-token cookie before giving up
    // and sending them back to the sign-in screen.
    if (res.status === 401 && !alreadyRetriedAfterRefresh) {
      const { refreshSession } = await import('@/lib/authApi')
      const refreshed = await refreshSession()
      if (refreshed) {
        return attempt(true)
      }
    }

    // Handle non-2xx responses before trying to read SSE stream
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const body = await res.json()
        const raw = body?.detail ?? body?.message
        if (raw !== undefined) {
          if (typeof raw === 'string') {
            detail = raw
          } else if (Array.isArray(raw)) {
            // FastAPI validation errors: [{loc, msg, type}, ...]
            detail = raw.map((e: { msg?: string }) => e.msg ?? JSON.stringify(e)).join('; ')
          } else {
            detail = JSON.stringify(raw)
          }
        }
      } catch { /* ignore parse errors */ }
      // Distinguish "please sign in" from other errors so callers (e.g.
      // the wizard's generate action) can redirect to /signup instead of
      // showing a generic retry-able error banner.
      onError(res.status === 401 ? 'AUTH_REQUIRED' : 'HTTP_ERROR', detail, res.status >= 500)
      return
    }

    const reader = res.body?.getReader()
    if (!reader) {
      onError('STREAM_ERROR', 'No response body from server.', true)
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let receivedData = false
    let receivedError = false

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
          receivedData = true
          onData(payload)
        } else if (event === 'error') {
          receivedError = true
          onError(payload.code, payload.message, payload.retryable)
        }
      }
    }

    // Stream ended without ever sending a data event — treat as a generation
    // failure. Bug fix: this used to fire unconditionally whenever no `data`
    // event arrived, even when the backend HAD already sent a specific, more
    // useful `error` event (e.g. LLM_TIMEOUT, GENERATION_FAILED) — that real
    // error was silently overwritten a moment later by this generic
    // "(NO_DATA)" message, since both call the same `onError` setter. Only
    // fall back to the generic message when the stream truly ended in
    // silence (no data AND no error event at all).
    if (!receivedData && !receivedError) {
      onError('NO_DATA', 'Itinerary generation did not complete. Please try again.', true)
    }
  }

  attempt(false).catch((err) => {
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
