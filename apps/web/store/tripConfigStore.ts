import { create } from 'zustand'
import type { TripConfig, GroupComposition, AccommodationPrefs, Budget, TripDates, OriginInput, DestinationInput } from '@/types'

const DEFAULT_GROUP: GroupComposition = {
  infants: 0, kids: [], adults: 1, seniors: 0, pets: 0,
}

const DEFAULT_ACCOMMODATION: AccommodationPrefs = {
  style: [], min_bedrooms: 1, bathrooms: 1,
  private_pool: false, kitchen: false,
  wheelchair_accessible: false, pet_friendly: false,
}

const DEFAULT_CONFIG: TripConfig = {
  purpose: '',
  dates: { start: null, end: null, flexible: false },
  scope: 'international',
  origin: { city: '', iata: '', lat: 0, lon: 0 },
  destination: null,
  destination_mode: 'fixed',
  destination_country: null,
  hops: [],
  themes: [],
  personas: [],
  group: DEFAULT_GROUP,
  accommodation: DEFAULT_ACCOMMODATION,
  pace: 'moderate',
  budget: { amount: 0, currency: 'INR' },
  splurge_categories: [],
  save_categories: [],
  prebooked_flights_inr: null,
  prebooked_accommodation_inr: null,
}

interface TripConfigStore {
  config: TripConfig
  updateConfig: (partial: Partial<TripConfig>) => void
  updateGroup: (partial: Partial<GroupComposition>) => void
  updateAccommodation: (partial: Partial<AccommodationPrefs>) => void
  updateBudget: (partial: Partial<Budget>) => void
  updateDates: (partial: Partial<TripDates>) => void
  setOrigin: (origin: OriginInput) => void
  setDestination: (dest: DestinationInput | null) => void
  addHop: (hop: DestinationInput) => void
  removeHop: (index: number) => void
  resetConfig: () => void
  /** Auto-applies Relaxed pace if any kid is under 5. Returns effective pace. */
  effectivePace: () => TripConfig['pace']
}

export const useTripConfigStore = create<TripConfigStore>((set, get) => ({
  config: DEFAULT_CONFIG,

  updateConfig: (partial) =>
    set((s) => ({ config: { ...s.config, ...partial } })),

  updateGroup: (partial) =>
    set((s) => ({ config: { ...s.config, group: { ...s.config.group, ...partial } } })),

  updateAccommodation: (partial) =>
    set((s) => ({ config: { ...s.config, accommodation: { ...s.config.accommodation, ...partial } } })),

  updateBudget: (partial) =>
    set((s) => ({ config: { ...s.config, budget: { ...s.config.budget, ...partial } } })),

  updateDates: (partial) =>
    set((s) => ({ config: { ...s.config, dates: { ...s.config.dates, ...partial } } })),

  setOrigin: (origin) =>
    set((s) => ({ config: { ...s.config, origin } })),

  setDestination: (destination) =>
    set((s) => ({ config: { ...s.config, destination } })),

  addHop: (hop) =>
    set((s) => ({
      config: {
        ...s.config,
        hops: s.config.hops.length < 5 ? [...s.config.hops, hop] : s.config.hops,
      },
    })),

  removeHop: (index) =>
    set((s) => ({
      config: { ...s.config, hops: s.config.hops.filter((_, i) => i !== index) },
    })),

  resetConfig: () => set({ config: DEFAULT_CONFIG }),

  effectivePace: () => {
    const { config } = get()
    // PRD: auto-Relaxed whenever any kid is under 5, regardless of user-selected pace
    const hasYoungKid = config.group.kids.some((k) => k.age < 5)
    if (hasYoungKid) return 'relaxed'
    return config.pace
  },
}))
