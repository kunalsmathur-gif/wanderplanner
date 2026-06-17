import { create } from 'zustand'

export type WizardPhase = 'chatting' | 'summary' | 'generating' | 'done'

export interface WizardMessage {
  id: string
  role: 'bot' | 'user'
  content: string
  chips?: string[]
  inputType?: 'text' | 'date' | 'number'
}

export type WizardField =
  | 'purpose' | 'origin' | 'destination_mode' | 'duration' | 'destination'
  | 'city_selection' | 'dates' | 'group' | 'budget' | 'accommodation' | 'pace' | 'themes'
  | 'refinement' | 'done'

interface WizardChatStore {
  messages: WizardMessage[]
  currentField: WizardField
  phase: WizardPhase
  collectedLabels: Record<string, string>

  addMessage: (msg: Omit<WizardMessage, 'id'>) => void
  setCurrentField: (f: WizardField) => void
  setPhase: (p: WizardPhase) => void
  addLabel: (key: string, value: string) => void
  reset: () => void
}

let wizardMessageId = 0
const nextId = () => `wizard-msg-${++wizardMessageId}`

const initialState = {
  messages: [] as WizardMessage[],
  currentField: 'purpose' as WizardField,
  phase: 'chatting' as WizardPhase,
  collectedLabels: {} as Record<string, string>,
}

export const useWizardChatStore = create<WizardChatStore>((set) => ({
  ...initialState,
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, { ...msg, id: nextId() }] })),
  setCurrentField: (currentField) => set({ currentField }),
  setPhase: (phase) => set({ phase }),
  addLabel: (key, value) => set((state) => ({
    collectedLabels: { ...state.collectedLabels, [key]: value },
  })),
  reset: () => set(initialState),
}))
