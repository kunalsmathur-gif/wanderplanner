import { create } from 'zustand'
import type { PinnedPOI } from '@/types'
import type { ItineraryDiff } from '@/lib/itineraryDiff'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  pins?: PinnedPOI[]      // verified pins to render as 📌 chips
  diff?: ItineraryDiff    // itinerary changes to render as added/removed/moved chips
}

type ChatStatus = 'idle' | 'sending' | 'error'

interface ChatStore {
  isOpen: boolean
  messages: ChatMessage[]
  status: ChatStatus
  errorMsg: string | null

  open: () => void
  close: () => void
  toggle: () => void
  addMessage: (msg: Omit<ChatMessage, 'id' | 'timestamp'>) => ChatMessage
  updateLastAssistant: (content: string, extras?: Pick<ChatMessage, 'pins' | 'diff'>) => void
  setStatus: (s: ChatStatus, err?: string) => void
  clearHistory: () => void
}

let _id = 0
function nextId() { return `msg-${++_id}` }

export const useChatStore = create<ChatStore>((set, get) => ({
  isOpen: false,
  messages: [],
  status: 'idle',
  errorMsg: null,

  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),
  toggle: () => set((s) => ({ isOpen: !s.isOpen })),

  addMessage: (msg) => {
    const full: ChatMessage = { ...msg, id: nextId(), timestamp: Date.now() }
    set((s) => ({ messages: [...s.messages, full] }))
    return full
  },

  updateLastAssistant: (content, extras) =>
    set((s) => {
      const msgs = [...s.messages]
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'assistant') {
          msgs[i] = { ...msgs[i], content, ...extras }
          break
        }
      }
      return { messages: msgs }
    }),

  setStatus: (status, err) => set({ status, errorMsg: err ?? null }),

  clearHistory: () => set({ messages: [], status: 'idle', errorMsg: null }),
}))
