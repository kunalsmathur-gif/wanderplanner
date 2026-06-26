import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type BookingType = 'Flight' | 'Hotel' | 'Activity' | 'Transport'

export interface Booking {
  id: string
  type: BookingType
  name: string
  confirmation: string
  date: string        // ISO date string
  amount: number      // in INR (0 if unknown)
  notes: string
}

interface BookingStore {
  bookings: Booking[]
  addBooking: (b: Omit<Booking, 'id'>) => void
  removeBooking: (id: string) => void
  updateBooking: (id: string, patch: Partial<Omit<Booking, 'id'>>) => void
}

let _seq = 0

export const useBookingStore = create<BookingStore>()(
  persist(
    (set) => ({
      bookings: [],

      addBooking: (b) =>
        set((s) => ({
          bookings: [
            ...s.bookings,
            { ...b, id: `bk-${Date.now()}-${++_seq}` },
          ],
        })),

      removeBooking: (id) =>
        set((s) => ({ bookings: s.bookings.filter((b) => b.id !== id) })),

      updateBooking: (id, patch) =>
        set((s) => ({
          bookings: s.bookings.map((b) => (b.id === id ? { ...b, ...patch } : b)),
        })),
    }),
    { name: 'wanderplan-bookings' }
  )
)
