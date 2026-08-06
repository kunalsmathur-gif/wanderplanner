// Shared TypeScript types — mirrors Pydantic models in apps/api/models/

export type Pace = 'relaxed' | 'moderate' | 'packed'
export type CrowdPreference = 'touristy' | 'balanced' | 'offbeat'
export type TripScope = 'local' | 'domestic' | 'international'
export type DestinationMode = 'fixed' | 'exploring' | 'country'

export interface KidAge { age: number }

export interface GroupComposition {
  infants: number      // 0-2 years
  kids: KidAge[]       // 2-8 years, individual ages
  adults: number       // 8+ years
  seniors: number      // 60+ years
  pets: number
}

export interface AccommodationPrefs {
  style: string[]
  min_bedrooms: number
  bathrooms: number
  private_pool: boolean
  kitchen: boolean
  wheelchair_accessible: boolean
  pet_friendly: boolean
}

export interface Budget {
  amount: number
  currency: string
}

export interface DestinationInput {
  city: string
  country: string
  lat: number
  lon: number
}

export interface OriginInput {
  city: string
  iata: string
  lat: number
  lon: number
}

export interface TripDates {
  start: string | null   // YYYY-MM-DD
  end: string | null
  flexible: boolean
  season?: string
  duration_days?: number  // Desired trip duration when dates are flexible
}

// Verified must-include place from a named-interest refinement (the "Harry
// Potter test"). Only the backend creates these, after OSM/wiki verification.
export interface PinnedPOI {
  name: string
  lat: number
  lon: number
  poi_type: string
  source_interest: string
  verified_by: 'osm' | 'wiki'
}

export interface TripConfig {
  purpose: string
  dates: TripDates
  scope: TripScope
  origin: OriginInput
  destination: DestinationInput | null
  destination_mode: DestinationMode
  destination_country: string | null   // used when mode = 'country'
  hops: DestinationInput[]             // multi-stop (max 5), used alongside destination
  themes: string[]
  personas: string[]
  group: GroupComposition
  accommodation: AccommodationPrefs
  pace: Pace
  crowd_preference: CrowdPreference   // hidden-gem curation dial
  budget: Budget
  splurge_categories: string[]
  save_categories: string[]
  prebooked_flights_inr: number | null
  prebooked_accommodation_inr: number | null
  pinned_pois: PinnedPOI[]             // verified hard constraints (max 8)
  day_cost_preferences: DayCostPreference[]  // per-day spend steering ("make day 3 cheaper")
}

// Itinerary types
export interface DayCostPreference {
  day_number: number
  direction: 'cheaper' | 'pricier'
}

export interface ItineraryItemLocation {
  lat: number
  lon: number
  address: string
}

export interface TransitWarning {
  between_items: string[]
  message: string
}

export interface ItineraryItem {
  id: string
  time_start: string
  time_end: string
  title: string
  local_name?: string          // Place name in local script (e.g. 浅草寺)
  description: string
  location: ItineraryItemLocation
  tags: string[]
  // What this one item costs the whole group in INR. 0 means genuinely free
  // (a beach, a walk) — there is no "unknown" state, see the backend model.
  // Excludes flights/accommodation, which are trip-level, not per-day.
  estimated_cost_inr?: number
  booking_url: string
  youtube_video_id: string
  youtube_search_query?: string // Pre-built YouTube search phrase
  alignment_score: number
  warnings: string[]
  // False when the post-generation verification pass couldn't match this
  // item's title against our ingested OSM/wiki corpus for the destination —
  // the LLM likely recalled it from training data, not from anything
  // Wanderplanner has verified. Defaults true server-side for paths that
  // never run the check (mock/cache/rag_skeleton, already curated/OSM-
  // sourced by construction), so only omit-safe here too.
  verified?: boolean
  // True when this item's coordinates sit implausibly far from the trip's
  // destination — a real place, but the wrong one (e.g. a London landmark
  // suggested for a Bali trip). Distinct from `verified` because it's a
  // higher-confidence, differently-worded defect.
  out_of_bounds?: boolean
}

export interface ItineraryDay {
  day_number: number
  date: string
  theme: string
  items: ItineraryItem[]
  transit_warnings: TransitWarning[]
  image_url?: string
  image_photographer?: string
  image_photographer_url?: string
}

export interface ItineraryResponse {
  days: ItineraryDay[]
  alignment_score: number
  warnings: string[]
  expense_breakdown: ExpenseBreakdown
  // "live" = real LLM generation, grounded in retrieved destination research.
  // "live_unverified" = the LLM call succeeded but there was no ingested
  // OSM/wiki/Reddit data for this destination at all, so the whole plan
  // came from the model's own training knowledge with nothing to check it
  // against. Anything else means the backend degraded to a fallback tier
  // (cache / rag_skeleton / enhanced_mock / mock) — the UI must disclose
  // this rather than present it as a verified plan.
  generation_tier?: GenerationTier
}

export type GenerationTier =
  | 'live'
  | 'live_unverified'
  | 'cache'
  | 'rag_skeleton'
  | 'enhanced_mock'
  | 'mock'

// Expense breakdown types
export interface ExpenseBreakdown {
  flights_inr: number
  visa_inr: number | null   // null = could not look it up; 0 = genuinely free
  accommodation_inr: number
  activities_inr: number
  food_inr: number
  local_transport_inr: number
  shopping_inr: number
  emergency_buffer_inr: number
  total_inr: number
  destination_currency_code: string
  total_destination_currency: number
  num_people: number
}

// Feasibility types
export interface CostBreakdown {
  flights_inr: number
  visa_inr: number | null   // null = could not look it up; 0 = genuinely free
  accommodation_inr: number
  daily_expenses_inr: number
  total_estimated_inr: number
}

export interface AlternativeDestination {
  city: string
  country: string
  estimated_total_inr: number
  why_cheaper: string
  similar_experiences: string[]
}

export interface FeasibilityResponse {
  feasible: boolean
  verdict: string
  budget_inr: number
  breakdown: CostBreakdown
  shortfall_inr: number
  buffer_inr: number
  bare_minimum_inr: number | null
  alternatives: AlternativeDestination[]
  disclaimer: string
}

// City recommendations (R15)
export interface RecommendedCity {
  name: string
  country: string
  reason: string
  lat: number
  lon: number
}

export interface RecommendCitiesResponse {
  cities: RecommendedCity[]
}

// Chat refinement action (R13)
export type ChatActionType = 'none' | 'patch_config' | 'regenerate'

export interface ChatRefineResponse {
  reply: string
  action_type: ChatActionType
  config_patch: Partial<TripConfig> | null
  major_change: boolean
  named_interest: string | null
  pinned_pois: PinnedPOI[]        // newly verified pins from this message
  dropped_candidates: string[]    // candidates that failed verification
}

export interface ComparisonParameter {
  parameter: string
  unit: string
  values: Record<string, string | number>
  winner: string
  highlight: string
}

export interface ComparisonResponse {
  comparison: ComparisonParameter[]
  partial_failures: string[]
}
