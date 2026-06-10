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
  themes: [],
  personas: [],
  group: DEFAULT_GROUP,
  accommodation: DEFAULT_ACCOMMODATION,
  pace: 'moderate',
  budget: { amount: 0, currency: 'USD' },
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

  resetConfig: () => set({ config: DEFAULT_CONFIG }),

  effectivePace: () => {
    const { config } = get()
    const hasYoungKid = config.group.kids.some((k) => k.age < 5)
    if (hasYoungKid && config.pace !== 'packed') return 'relaxed'
    return config.pace
  },
}))
