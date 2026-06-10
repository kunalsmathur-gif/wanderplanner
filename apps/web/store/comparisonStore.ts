import { create } from 'zustand'
import type { ComparisonResponse, DestinationInput } from '@/types'

type ComparisonStatus = 'idle' | 'loading' | 'success' | 'partial' | 'error'

interface ComparisonStore {
  destinationA: DestinationInput | null
  destinationB: DestinationInput | null
  result: ComparisonResponse | null
  status: ComparisonStatus
  setDestinations: (a: DestinationInput, b: DestinationInput) => void
  setResult: (result: ComparisonResponse) => void
  setStatus: (status: ComparisonStatus) => void
  reset: () => void
}

export const useComparisonStore = create<ComparisonStore>((set) => ({
  destinationA: null,
  destinationB: null,
  result: null,
  status: 'idle',
  setDestinations: (destinationA, destinationB) => set({ destinationA, destinationB }),
  setResult: (result) => set({ result, status: result.partial_failures.length ? 'partial' : 'success' }),
  setStatus: (status) => set({ status }),
  reset: () => set({ destinationA: null, destinationB: null, result: null, status: 'idle' }),
}))
