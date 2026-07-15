// Server-side fetch for shared trips (SSR + OG metadata + opengraph-image all
// need the same payload from the FastAPI in-memory share store).
import type { ItineraryDay, ExpenseBreakdown } from '@/types'

export interface SharedTripData {
  itinerary: { days: ItineraryDay[]; alignment_score: number; expense_breakdown?: ExpenseBreakdown }
  trip_config: Record<string, unknown>
  labels: Record<string, string>
  destination_label: string
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export async function getSharedTrip(slug: string): Promise<SharedTripData | null> {
  try {
    // Share links are ephemeral (in-memory store, no revalidation window that
    // makes sense) — always fetch fresh so unfurls never show stale/expired data.
    const res = await fetch(`${BASE_URL}/api/share/${slug}`, { cache: 'no-store' })
    if (!res.ok) return null
    return (await res.json()) as SharedTripData
  } catch {
    return null
  }
}
