import * as React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatPanel } from '@/components/chat/ChatPanel'
import { useChatStore } from '@/store/chatStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { chatRefine } from '@/lib/api'

// 🔴 Reported live: the post-itinerary "Ask & adjust" chat had no voice CTA
// at all — unlike the wizard's own mic button (components/wizard/LLMWizard.tsx),
// even though hooks/useVoice.ts is already generic enough to reuse here
// unmodified. These tests pin the new CTA: a mic button that starts a spoken
// conversation and threads a transcript through to the same chatRefine() call
// a typed message would use.

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/lib/resumeLastItinerary', () => ({
  loadLastItinerary: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  chatRefine: vi.fn(),
  streamItinerary: vi.fn(),
  checkFeasibility: vi.fn(),
  sendGenerationSignal: vi.fn(),
  synthesizeVoice: vi.fn(),
}))

// Same fake as __tests__/hooks/useVoice.test.tsx — jsdom implements neither
// half of the Web Speech API.
class FakeRecognition {
  static instances: FakeRecognition[] = []
  continuous = false
  interimResults = false
  lang = ''
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null = null
  onerror: ((e: { error?: string }) => void) | null = null
  onend: (() => void) | null = null

  constructor() {
    FakeRecognition.instances.push(this)
  }

  start() {}
  stop() { this.onend?.() }

  speech(transcript: string) {
    this.onresult?.({ results: [[{ transcript }]] })
    this.onend?.()
  }
}

function installSpeechApis() {
  FakeRecognition.instances = []
  Object.defineProperty(window, 'SpeechRecognition', {
    value: FakeRecognition, configurable: true, writable: true,
  })
  Object.defineProperty(window, 'speechSynthesis', {
    value: { getVoices: () => [], cancel: vi.fn(), speak: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() },
    configurable: true, writable: true,
  })
  Object.defineProperty(window, 'SpeechSynthesisUtterance', {
    value: class { constructor(public text: string) {} },
    configurable: true, writable: true,
  })
}

function uninstallSpeechApis() {
  for (const key of ['SpeechRecognition', 'speechSynthesis', 'SpeechSynthesisUtterance']) {
    Reflect.deleteProperty(window, key)
  }
}

const latestRec = () => FakeRecognition.instances[FakeRecognition.instances.length - 1]!

const initialChatState = useChatStore.getState()
const initialTripConfigState = useTripConfigStore.getState()
const initialItineraryState = useItineraryStore.getState()

describe('ChatPanel — voice mode CTA', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    installSpeechApis()
    useChatStore.setState({ ...initialChatState, isOpen: true })
  })

  afterEach(() => {
    useChatStore.setState(initialChatState)
    useTripConfigStore.setState(initialTripConfigState)
    useItineraryStore.setState(initialItineraryState)
    uninstallSpeechApis()
  })

  it('renders an enabled mic button in the header and the input row when the browser supports it', () => {
    render(<ChatPanel />)
    expect(screen.getByRole('button', { name: /start voice mode/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /^voice input$/i })).toBeEnabled()
  })

  it('asks which language to speak the first time voice mode is turned on', async () => {
    const user = userEvent.setup()
    render(<ChatPanel />)

    await user.click(screen.getByRole('button', { name: /start voice mode/i }))

    expect(await screen.findByText(/which language would you like to speak/i)).toBeInTheDocument()
  })

  it('starts listening once a language is chosen, then sends the recognized transcript through chatRefine', async () => {
    vi.mocked(chatRefine).mockResolvedValue({
      reply: 'Got it!',
      action_type: 'none',
      major_change: false,
      config_patch: null,
      named_interest: null,
      pinned_pois: [],
      dropped_candidates: [],
    } as never)

    const user = userEvent.setup()
    render(<ChatPanel />)

    await user.click(screen.getByRole('button', { name: /start voice mode/i }))
    const englishOption = await screen.findByRole('button', { name: /speak and listen in english/i })
    await user.click(englishOption)

    expect(await screen.findByText(/listening in english/i)).toBeInTheDocument()

    latestRec().speech('reduce budget for day 4')

    await waitFor(() => expect(chatRefine).toHaveBeenCalled())
    const [history] = vi.mocked(chatRefine).mock.calls[0]!
    expect(history.at(-1)).toMatchObject({ role: 'user', content: 'reduce budget for day 4' })
  })
})
