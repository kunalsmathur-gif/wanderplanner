import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useVoice } from '@/hooks/useVoice'
import { synthesizeVoice, TtsRequestError } from '@/lib/api'

// The real module talks to the network; the server-voice path is exercised
// against this mock instead (see "useVoice — server-synthesized voice"
// below). Kept a `TtsRequestError` re-export so tests can throw the same
// class the hook's `catch` block checks with `instanceof`.
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, synthesizeVoice: vi.fn() }
})

// ── Web Speech API fakes ──────────────────────────────────────────────────
// jsdom implements neither half of the Web Speech API, so both are stubbed
// here. The fakes deliberately reproduce the ordering that broke the original
// implementation: `onresult` and `onend` both fire while the reply is still in
// flight, seconds before anything calls speakReply().

class FakeRecognition {
  static instances: FakeRecognition[] = []
  static startThrows = false

  continuous = false
  interimResults = false
  lang = ''
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null = null
  onerror: ((e: { error?: string }) => void) | null = null
  onend: (() => void) | null = null
  started = false

  constructor() {
    FakeRecognition.instances.push(this)
  }

  start() {
    if (FakeRecognition.startThrows) throw new Error('InvalidStateError')
    this.started = true
  }

  stop() {
    this.started = false
    this.onend?.()
  }

  /** The user spoke; recognition returns a transcript and then closes. */
  speech(transcript: string) {
    this.onresult?.({ results: [[{ transcript }]] })
    this.onend?.()
  }

  fail(code: string) {
    this.onerror?.({ error: code })
    this.onend?.()
  }
}

class FakeUtterance {
  lang = ''
  voice: SpeechSynthesisVoice | null = null
  rate = 1
  pitch = 1
  volume = 1
  onstart: (() => void) | null = null
  onend: (() => void) | null = null
  onerror: ((e: { error?: string }) => void) | null = null
  constructor(public text: string) {}
}

function makeVoice(name: string, lang: string): SpeechSynthesisVoice {
  return { name, lang, default: false, localService: true, voiceURI: name } as SpeechSynthesisVoice
}

const EN_VOICE = makeVoice('Microsoft Heera Female', 'en-IN')
const HI_VOICE = makeVoice('Google हिन्दी', 'hi-IN')

class FakeSynth {
  spoken: FakeUtterance[] = []
  cancelCount = 0
  voices: SpeechSynthesisVoice[] = [EN_VOICE]
  private listeners: (() => void)[] = []

  getVoices() { return this.voices }
  speak(u: FakeUtterance) { this.spoken.push(u) }
  cancel() { this.cancelCount++ }
  addEventListener(_: string, fn: () => void) { this.listeners.push(fn) }
  removeEventListener(_: string, fn: () => void) {
    this.listeners = this.listeners.filter((l) => l !== fn)
  }

  /** Chrome loads voices asynchronously and announces them like this. */
  emitVoicesChanged(voices: SpeechSynthesisVoice[]) {
    this.voices = voices
    this.listeners.forEach((l) => l())
  }

  /**
   * Utterances that actually say something.
   *
   * Turning voice mode on speaks a silent zero-volume space to satisfy iOS
   * Safari's user-gesture requirement, so `spoken` always carries one extra
   * entry. Assertions want the real replies.
   */
  get real() { return this.spoken.filter((u) => u.text.trim().length > 0) }

  get last() { return this.real[this.real.length - 1]! }
}

let synth: FakeSynth

function installSpeechApis({ recognition = true, synthesis = true } = {}) {
  FakeRecognition.instances = []
  FakeRecognition.startThrows = false
  synth = new FakeSynth()

  if (recognition) {
    Object.defineProperty(window, 'SpeechRecognition', {
      value: FakeRecognition, configurable: true, writable: true,
    })
  }
  if (synthesis) {
    Object.defineProperty(window, 'speechSynthesis', {
      value: synth, configurable: true, writable: true,
    })
    Object.defineProperty(window, 'SpeechSynthesisUtterance', {
      value: FakeUtterance, configurable: true, writable: true,
    })
  }
}

function uninstallSpeechApis() {
  for (const key of ['SpeechRecognition', 'webkitSpeechRecognition', 'speechSynthesis', 'SpeechSynthesisUtterance']) {
    Reflect.deleteProperty(window, key)
  }
}

const latestRec = () => FakeRecognition.instances[FakeRecognition.instances.length - 1]!

beforeEach(() => installSpeechApis())
afterEach(() => { uninstallSpeechApis(); vi.restoreAllMocks() })

// ── The regression this whole milestone exists for ────────────────────────

describe('useVoice — Anya actually speaks her reply', () => {
  it('speaks after a voice-driven turn, even though recognition has already ended', () => {
    // The original bug, in the original order. `toggleVoice()` assigned
    // `onresult` and *then* set voiceActive, so the handler held a render
    // where the flag was false; and `onend` cleared the flag anyway, long
    // before the API replied. Either alone means silence.
    const onTranscript = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript }))

    act(() => { result.current.toggleVoiceMode() })
    act(() => { latestRec().speech('a beach trip to Goa') })

    expect(onTranscript).toHaveBeenCalledWith('a beach trip to Goa')
    // Recognition is over; the mode is not.
    expect(result.current.isListening).toBe(false)
    expect(result.current.voiceMode).toBe(true)

    // The reply lands some seconds later.
    act(() => { result.current.speakReply('Goa is a wonderful choice!') })

    expect(synth.real).toHaveLength(1)
    expect(synth.last.text).toBe('Goa is a wonderful choice!')
  })

  it('stays silent when voice mode was never switched on', () => {
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.speakReply('Goa is a wonderful choice!') })
    expect(synth.real).toHaveLength(0)
  })

  it('speaks Hindi replies rather than dropping them', () => {
    // sanitiseForSpeech has its own coverage; this asserts the hook does not
    // reintroduce the empty-string bail on the way through.
    synth.voices = [EN_VOICE, HI_VOICE]
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })
    act(() => { result.current.setLang('hi') })
    act(() => { result.current.speakReply('गोवा बहुत सुंदर है।') })

    expect(synth.last.text).toBe('गोवा बहुत सुंदर है।')
    expect(synth.last.lang).toBe('hi-IN')
  })
})

// ── iOS gesture unlock ────────────────────────────────────────────────────

describe('useVoice — synthesiser priming', () => {
  it('speaks a silent utterance inside the toggle, for iOS Safari', () => {
    // iOS only permits speechSynthesis.speak() from within a user gesture,
    // and Anya's first real utterance arrives after an awaited API call —
    // well outside the tap. Priming during the tap unlocks the session.
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })

    expect(synth.spoken).toHaveLength(1)
    expect(synth.spoken[0]!.text.trim()).toBe('')
    expect(synth.spoken[0]!.volume).toBe(0)   // inaudible on every platform
  })

  it('primes once per session, not on every toggle', () => {
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })
    act(() => { result.current.toggleVoiceMode() })
    act(() => { result.current.toggleVoiceMode() })

    expect(synth.spoken.filter((u) => !u.text.trim())).toHaveLength(1)
  })

  it('does not prime when the browser cannot recognise speech', () => {
    // No point unlocking audio for a conversation that cannot start.
    uninstallSpeechApis()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })
    expect(result.current.voiceMode).toBe(false)
  })
})

// ── Mode vs. mic ──────────────────────────────────────────────────────────

describe('useVoice — voiceMode and isListening are separate', () => {
  it('ends the mic but keeps the mode when recognition closes', () => {
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })
    expect(result.current.isListening).toBe(true)

    act(() => { latestRec().onend?.() })

    expect(result.current.isListening).toBe(false)
    expect(result.current.voiceMode).toBe(true)
  })

  it('toggling off stops both and cancels speech', () => {
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })
    act(() => { result.current.toggleVoiceMode() })

    expect(result.current.voiceMode).toBe(false)
    expect(result.current.isListening).toBe(false)
    expect(synth.cancelCount).toBeGreaterThan(0)
  })

  it('re-arms the mic once Anya finishes speaking, and not before', () => {
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })
    act(() => { latestRec().speech('Goa') })
    act(() => { result.current.speakReply('Lovely choice!') })

    // Mic must stay shut while audio plays or it transcribes Anya back.
    act(() => { synth.last.onstart?.() })
    expect(result.current.isListening).toBe(false)
    expect(result.current.isSpeaking).toBe(true)

    act(() => { synth.last.onend?.() })
    expect(result.current.isSpeaking).toBe(false)
    expect(result.current.isListening).toBe(true)
  })

  it('does not re-arm when the caller says listening is over', () => {
    // The wizard passes `phase === 'chatting'`; generation has begun here.
    const { result } = renderHook(() =>
      useVoice({ onTranscript: vi.fn(), canListen: () => false }),
    )
    act(() => { result.current.toggleVoiceMode() })
    act(() => { latestRec().speech('Goa') })
    act(() => { result.current.speakReply('Generating now.') })
    act(() => { synth.last.onend?.() })

    expect(result.current.isListening).toBe(false)
  })

  it('ignores a blank transcript', () => {
    const onTranscript = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript }))
    act(() => { result.current.toggleVoiceMode() })
    act(() => { latestRec().speech('   ') })
    expect(onTranscript).not.toHaveBeenCalled()
  })
})

// ── Unsupported browsers ──────────────────────────────────────────────────

describe('useVoice — browsers without SpeechRecognition', () => {
  it('reports unsupported instead of doing nothing at all', () => {
    // Firefox has never shipped SpeechRecognition. The button was rendered
    // unconditionally and the handler did `if (!Ctor) return`, so a click
    // produced no state change and no message — a dead control.
    uninstallSpeechApis()
    const onNotice = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice }))

    expect(result.current.supported).toBe(false)
    act(() => { result.current.toggleVoiceMode() })

    expect(onNotice).toHaveBeenCalledWith(expect.stringMatching(/isn’t supported/i))
    expect(result.current.voiceMode).toBe(false)
  })

  it('reports supported where the API exists', () => {
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    expect(result.current.supported).toBe(true)
  })

  it('accepts the webkit-prefixed constructor', () => {
    uninstallSpeechApis()
    Object.defineProperty(window, 'webkitSpeechRecognition', {
      value: FakeRecognition, configurable: true, writable: true,
    })
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    expect(result.current.supported).toBe(true)
  })

  it('surfaces a failure to start the microphone', () => {
    FakeRecognition.startThrows = true
    const onNotice = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice }))
    act(() => { result.current.toggleVoiceMode() })

    expect(onNotice).toHaveBeenCalledWith(expect.stringMatching(/couldn’t start the microphone/i))
    expect(result.current.isListening).toBe(false)
  })
})

// ── Errors reach the user ─────────────────────────────────────────────────

describe('useVoice — recognition errors', () => {
  it('tells the user when microphone permission is denied', () => {
    const onNotice = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice }))
    act(() => { result.current.toggleVoiceMode() })
    act(() => { latestRec().fail('not-allowed') })

    expect(onNotice).toHaveBeenCalledWith(expect.stringMatching(/microphone access is blocked/i))
    expect(result.current.isListening).toBe(false)
  })

  it('says nothing for aborted, which is our own stop()', () => {
    const onNotice = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice }))
    act(() => { result.current.toggleVoiceMode() })
    act(() => { latestRec().fail('aborted') })

    expect(onNotice).not.toHaveBeenCalled()
  })

  it('reports a synthesis failure and still re-arms the mic', () => {
    const onNotice = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice }))
    act(() => { result.current.toggleVoiceMode() })
    act(() => { latestRec().onend?.() })
    act(() => { result.current.speakReply('Lovely choice!') })
    act(() => { synth.last.onerror?.({ error: 'audio-busy' }) })

    expect(onNotice).toHaveBeenCalledWith(expect.stringMatching(/audio output is unavailable/i))
    expect(result.current.isListening).toBe(true)
  })

  it('ignores the interrupted event our own cancel() raises', () => {
    const onNotice = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice }))
    act(() => { result.current.toggleVoiceMode() })
    act(() => { result.current.speakReply('Lovely choice!') })
    act(() => { synth.last.onerror?.({ error: 'interrupted' }) })

    expect(onNotice).not.toHaveBeenCalled()
  })
})

// ── Voice selection ───────────────────────────────────────────────────────

describe('useVoice — voice loading', () => {
  it('uses voices that arrive after mount', () => {
    // getVoices() returns [] on a cold load until `voiceschanged` fires, and
    // there was no listener — so the first utterance of a session, the one
    // that sets the tone, always used the platform default voice.
    synth.voices = []
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })
    act(() => { synth.emitVoicesChanged([EN_VOICE]) })
    act(() => { result.current.speakReply('Lovely choice!') })

    expect(synth.last.voice).toBe(EN_VOICE)
  })

  it('warns the moment Hindi is selected, before Anya ever replies', () => {
    // Finding out three turns in that the device cannot speak Hindi is worse
    // than being told when you pick it.
    synth.voices = [EN_VOICE]  // no Hindi voice installed
    const onNotice = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice }))

    act(() => { result.current.setLang('hi') })

    expect(onNotice).toHaveBeenCalledWith(expect.stringMatching(/no hindi voice is installed/i))
  })

  it('does not warn when the language is speakable', () => {
    synth.voices = [EN_VOICE, HI_VOICE]
    const onNotice = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice }))
    act(() => { result.current.setLang('hi') })
    expect(onNotice).not.toHaveBeenCalled()
  })

  it('warns once, not on every turn', () => {
    synth.voices = [EN_VOICE]
    const onNotice = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice }))
    act(() => { result.current.toggleVoiceMode() })
    act(() => { result.current.setLang('hi') })
    act(() => { result.current.speakReply('गोवा बहुत सुंदर है।') })
    act(() => { result.current.speakReply('और कुछ?') })

    expect(onNotice).toHaveBeenCalledTimes(1)
  })

  it('warns once voices load, when the choice could not be judged yet', () => {
    // getVoices() is empty until `voiceschanged` fires, so a language picked
    // on a cold load cannot be assessed at the time it is picked.
    synth.voices = []
    const onNotice = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice }))

    act(() => { result.current.setLang('hi') })
    expect(onNotice).not.toHaveBeenCalled()   // unknown, not absent

    act(() => { synth.emitVoicesChanged([EN_VOICE]) })
    expect(onNotice).toHaveBeenCalledWith(expect.stringMatching(/no hindi voice is installed/i))
  })

  it('clears the warning when switching back to a speakable language', () => {
    synth.voices = [EN_VOICE]
    const onNotice = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice }))
    act(() => { result.current.setLang('hi') })
    act(() => { result.current.setLang('en') })
    act(() => { result.current.setLang('hi') })

    // Warned again after a genuine round trip, rather than staying silent
    // forever once dismissed.
    expect(onNotice).toHaveBeenCalledTimes(2)
  })

  it('warns and skips speech when no voice exists for the language', () => {
    synth.voices = [EN_VOICE]  // no Hindi voice installed
    const onNotice = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice }))
    act(() => { result.current.toggleVoiceMode() })
    act(() => { result.current.setLang('hi') })
    act(() => { result.current.speakReply('गोवा बहुत सुंदर है।') })

    expect(onNotice).toHaveBeenCalledWith(expect.stringMatching(/no hindi voice is installed/i))
    expect(synth.real).toHaveLength(0)
    // The conversation must continue by text rather than dead-ending.
    expect(result.current.isListening).toBe(true)
  })

  it('applies Anya’s prosody settings', () => {
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })
    act(() => { result.current.speakReply('Lovely choice!') })

    expect(synth.last.rate).toBeCloseTo(1.05)
    expect(synth.last.pitch).toBeCloseTo(1.15)
  })
})

// ── Language ──────────────────────────────────────────────────────────────

describe('useVoice — language selection', () => {
  it('defaults to English', () => {
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })
    expect(result.current.lang).toBe('en')
    expect(latestRec().lang).toBe('en-IN')
  })

  it('listens in Hindi once switched', () => {
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.setLang('hi') })
    act(() => { result.current.toggleVoiceMode() })
    expect(latestRec().lang).toBe('hi-IN')
  })

  it('restarts a live recognition session so the new language takes effect', () => {
    // `lang` is read at start() time only, so an open session keeps listening
    // in the old language until it is torn down and rebuilt.
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })
    const before = FakeRecognition.instances.length

    act(() => { result.current.setLang('hi') })

    expect(FakeRecognition.instances.length).toBe(before + 1)
    expect(latestRec().lang).toBe('hi-IN')
    expect(result.current.isListening).toBe(true)
  })

  it('does not restart when the language is unchanged', () => {
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })
    const before = FakeRecognition.instances.length
    act(() => { result.current.setLang('en') })
    expect(FakeRecognition.instances.length).toBe(before)
  })
})

// ── Teardown ──────────────────────────────────────────────────────────────

describe('useVoice — unmount', () => {
  it('stops recognition and cancels speech', () => {
    const { result, unmount } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })
    const rec = latestRec()
    const cancelsBefore = synth.cancelCount

    unmount()

    expect(rec.started).toBe(false)
    expect(synth.cancelCount).toBeGreaterThan(cancelsBefore)
  })
})

// ── Server-synthesized voice (docs/adr/0001-anya-voice-provider.md) ───────

class FakeAudio {
  static instances: FakeAudio[] = []
  src = ''
  volume = 1
  onplay: (() => void) | null = null
  onended: (() => void) | null = null
  onerror: (() => void) | null = null
  played = false
  paused = true

  constructor() {
    FakeAudio.instances.push(this)
  }

  play() {
    this.played = true
    this.paused = false
    this.onplay?.()
    return Promise.resolve()
  }

  pause() {
    this.paused = true
  }
}

const mockedSynthesizeVoice = vi.mocked(synthesizeVoice)

function installAudioApis() {
  FakeAudio.instances = []
  Object.defineProperty(window, 'Audio', { value: FakeAudio, configurable: true, writable: true })
  Object.defineProperty(URL, 'createObjectURL', {
    value: vi.fn(() => 'blob:fake-url'), configurable: true, writable: true,
  })
  Object.defineProperty(URL, 'revokeObjectURL', {
    value: vi.fn(), configurable: true, writable: true,
  })
}

describe('useVoice — server-synthesized voice', () => {
  beforeEach(() => {
    installAudioApis()
    mockedSynthesizeVoice.mockReset()
  })

  it('plays Anya\'s real server-synthesized audio instead of speechSynthesis when a signature is present', async () => {
    const blob = new Blob(['fake-audio'], { type: 'audio/ogg' })
    mockedSynthesizeVoice.mockResolvedValue(blob)
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })

    await act(async () => {
      result.current.speakReply('Goa is a wonderful choice!', 'sig-123')
    })

    expect(mockedSynthesizeVoice).toHaveBeenCalledWith(
      'Goa is a wonderful choice!', expect.any(String), 'sig-123',
    )
    // Never falls back to the browser voice — that fallback is the exact
    // "different Anya on every device" bug this path exists to retire.
    expect(synth.real).toHaveLength(0)
    expect(FakeAudio.instances[0]!.played).toBe(true)
  })

  it('falls back to browser speechSynthesis when no signature is provided', async () => {
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn() }))
    act(() => { result.current.toggleVoiceMode() })

    await act(async () => {
      result.current.speakReply('Goa is a wonderful choice!')
    })

    expect(mockedSynthesizeVoice).not.toHaveBeenCalled()
    expect(synth.last.text).toBe('Goa is a wonderful choice!')
  })

  it('surfaces a text notice and stays silent on synthesis failure, without falling back to speechSynthesis', async () => {
    mockedSynthesizeVoice.mockRejectedValue(new TtsRequestError('tts_unavailable'))
    const onNotice = vi.fn()
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onNotice }))
    act(() => { result.current.toggleVoiceMode() })

    await act(async () => {
      result.current.speakReply('Goa is a wonderful choice!', 'sig-123')
    })

    expect(synth.real).toHaveLength(0)
    expect(onNotice).toHaveBeenCalled()
  })
})
