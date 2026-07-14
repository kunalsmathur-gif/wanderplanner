// Itinerary diff for the visible-refinement-diff UI (GTM §2, "Harry Potter
// test"): after a refinement regenerates the plan, show the user exactly what
// changed as chips in the Anya panel — added / removed / moved items, matched
// across versions by title similarity. Pure client-side, O(old × new) over a
// few dozen items — no API cost.
import type { ItineraryDay } from '@/types'

export interface DiffEntry {
  title: string
  day: number // day_number it appears on (new day for added/moved, old day for removed)
  fromDay?: number // only for moved
}

export interface ItineraryDiff {
  added: DiffEntry[]
  removed: DiffEntry[]
  moved: DiffEntry[]
}

interface FlatItem {
  title: string
  norm: string
  tokens: Set<string>
  day: number
}

function normalize(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

// Generic words that shouldn't drive a match ("visit", "tour", city fillers).
const STOP_WORDS = new Set([
  'the', 'a', 'an', 'at', 'of', 'in', 'to', 'and', 'visit', 'explore', 'tour',
  'morning', 'afternoon', 'evening', 'day', 'walk', 'local', 'trip',
])

function tokens(norm: string): Set<string> {
  return new Set(norm.split(' ').filter((t) => t.length > 2 && !STOP_WORDS.has(t)))
}

function flatten(days: ItineraryDay[]): FlatItem[] {
  return days.flatMap((d) =>
    d.items.map((i) => {
      const norm = normalize(i.title)
      return { title: i.title, norm, tokens: tokens(norm), day: d.day_number }
    }),
  )
}

/** Same place across regenerations? Exact normalized match, containment, or
 * strong token overlap (Jaccard ≥ 0.6) — titles drift slightly between LLM
 * runs ("Senso-ji Temple" vs "Visit Senso-ji Temple, Asakusa"). */
function sameItem(a: FlatItem, b: FlatItem): boolean {
  if (a.norm === b.norm) return true
  if (a.norm.length >= 6 && (b.norm.includes(a.norm) || a.norm.includes(b.norm))) return true
  if (a.tokens.size === 0 || b.tokens.size === 0) return false
  let shared = 0
  for (const t of a.tokens) if (b.tokens.has(t)) shared++
  const union = a.tokens.size + b.tokens.size - shared
  return union > 0 && shared / union >= 0.6
}

export function diffItineraries(oldDays: ItineraryDay[], newDays: ItineraryDay[]): ItineraryDiff {
  const oldItems = flatten(oldDays)
  const newItems = flatten(newDays)

  const matchedNew = new Set<number>()
  const diff: ItineraryDiff = { added: [], removed: [], moved: [] }

  for (const oldItem of oldItems) {
    const matchIdx = newItems.findIndex((n, idx) => !matchedNew.has(idx) && sameItem(oldItem, n))
    if (matchIdx === -1) {
      diff.removed.push({ title: oldItem.title, day: oldItem.day })
    } else {
      matchedNew.add(matchIdx)
      const match = newItems[matchIdx]
      if (match.day !== oldItem.day) {
        diff.moved.push({ title: match.title, day: match.day, fromDay: oldItem.day })
      }
    }
  }

  newItems.forEach((n, idx) => {
    if (!matchedNew.has(idx)) diff.added.push({ title: n.title, day: n.day })
  })

  return diff
}

export function isEmptyDiff(diff: ItineraryDiff): boolean {
  return diff.added.length === 0 && diff.removed.length === 0 && diff.moved.length === 0
}
