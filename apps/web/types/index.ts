// Shared TypeScript types — mirrors Pydantic models in apps/api/models/

export type Pace = 'relaxed' | 'moderate' | 'packed'
export type TripScope = 'local' | 'domestic' | 'international'
export type DestinationMode = 'fixed' | 'exploring'

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
}

export interface TripConfig {
  purpose: string
  dates: TripDates
  scope: TripScope
  origin: OriginInput
  destination: DestinationInput | null
  destination_mode: DestinationMode
  themes: string[]
  personas: string[]
  group: GroupComposition
  accommodation: AccommodationPrefs
  pace: Pace
  budget: Budget
}

// Itinerary types
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
  booking_url: string
  youtube_video_id: string
  youtube_search_query?: string // Pre-built YouTube search phrase
  alignment_score: number
  warnings: string[]
}

export interface ItineraryDay {
  day_number: number
  date: string
  theme: string
  items: ItineraryItem[]
  transit_warnings: TransitWarning[]
}

export interface ItineraryResponse {
  days: ItineraryDay[]
  alignment_score: number
  warnings: string[]
}

// Feasibility types
export interface CostBreakdown {
  flights_inr: number
  visa_inr: number
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
  alternatives: AlternativeDestination[]
  disclaimer: string
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
