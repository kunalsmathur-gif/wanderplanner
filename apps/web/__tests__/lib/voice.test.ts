import { describe, it, expect } from 'vitest'
import {
  VOICE_LANGS,
  hasVoiceForLang,
  missingVoiceMessage,
  pickVoice,
  recognitionErrorMessage,
  sanitiseForSpeech,
  synthesisErrorMessage,
} from '@/lib/voice'

/** Minimal stand-in for SpeechSynthesisVoice — pickVoice reads two fields. */
function voice(name: string, lang: string): SpeechSynthesisVoice {
  return { name, lang, default: false, localService: true, voiceURI: name } as SpeechSynthesisVoice
}

describe('sanitiseForSpeech — Devanagari', () => {
  // The bug this replaced: `[^\w\s.,!?'₹%-]` with JS's always-ASCII \w
  // stripped every Devanagari character, so `clean` came out empty and the
  // caller's `if (!clean) return` made text-to-speech say nothing at all.
  it('keeps a Hindi sentence intact', () => {
    const hindi = 'मुझे गोवा जाना है'
    expect(sanitiseForSpeech(hindi)).toBe(hindi)
  })

  it('keeps combining vowel signs, not just the consonants', () => {
    // खाना is ख + ा + न + ा. Dropping the matras yields खन — a real word
    // meaning something else, spoken confidently. Worse than silence.
    const word = 'खाना'
    const out = sanitiseForSpeech(word)
    expect(out).toBe(word)
    expect(out).not.toBe('खन')
    expect(Array.from(out)).toHaveLength(4)
  })

  it('keeps conjuncts formed with a virama', () => {
    expect(sanitiseForSpeech('क्षत्रिय')).toBe('क्षत्रिय')
  })

  it('keeps ZWJ and ZWNJ, which are load-bearing in conjuncts', () => {
    const withZwj = 'नमस्ते‍दुनिया'
    expect(sanitiseForSpeech(withZwj)).toBe(withZwj)
    const withZwnj = 'क‌ष'
    expect(sanitiseForSpeech(withZwnj)).toBe(withZwnj)
  })

  it('keeps the danda, the Devanagari full stop', () => {
    // Allowing '.' but not '।' would run every Hindi sentence together.
    expect(sanitiseForSpeech('गोवा सुंदर है। कब जाना है?')).toBe('गोवा सुंदर है। कब जाना है?')
  })

  it('keeps a Devanagari price', () => {
    expect(sanitiseForSpeech('₹25,000 प्रति व्यक्ति')).toBe('₹25,000 प्रति व्यक्ति')
  })
})

describe('sanitiseForSpeech — ASCII behaviour is unchanged', () => {
  it('strips markdown emphasis marks', () => {
    expect(sanitiseForSpeech('**Goa** is _lovely_')).toBe('Goa is lovely')
  })

  it('unwraps markdown links to their label', () => {
    expect(sanitiseForSpeech('See [the beach](https://example.com/x)')).toBe('See the beach')
  })

  it('keeps prices, percentages and sentence punctuation', () => {
    // The em dash is not in the allowlist; the gap it leaves is collapsed
    // rather than left as a double space.
    expect(sanitiseForSpeech("₹25,000 — that's 10% off, right?")).toBe(
      "₹25,000 that's 10% off, right?",
    )
  })

  it('strips emoji', () => {
    expect(sanitiseForSpeech('Leisure 🌴 sounds great')).toBe('Leisure sounds great')
  })

  it('collapses the whitespace left behind by removals', () => {
    expect(sanitiseForSpeech('Goa   🌴🌴   beaches')).toBe('Goa beaches')
  })
})

describe('sanitiseForSpeech — nothing to say', () => {
  it('returns empty for empty input', () => {
    expect(sanitiseForSpeech('')).toBe('')
  })

  it('returns empty for an emoji-only reply', () => {
    expect(sanitiseForSpeech('🎉🎉🎉')).toBe('')
  })

  it('returns empty when only invisible joiners survive', () => {
    // ZWJ is deliberately preserved, so an emoji ZWJ sequence cleans down to
    // bare joiners: non-empty to a truthiness check, silent to a synthesiser.
    expect(sanitiseForSpeech('👨‍👩‍👧')).toBe('')
  })

  it('returns empty for punctuation-only input', () => {
    expect(sanitiseForSpeech('... !!! ---')).toBe('')
  })
})

describe('pickVoice — Anya is a woman', () => {
  // The Web Speech API exposes no gender field: name, lang, default,
  // localService, voiceURI is the whole interface. Windows *does* record it
  // (Attributes\Gender in the registry — Heera is Female, Ravi is Male), but
  // the browser drops it, so matching names is the only lever available.
  it('picks the female voice from a real Windows 11 voice list', () => {
    // Exactly what getVoices() returned on the dev machine, in order. Neither
    // Indian voice has "female" in its name, so the old rule fell through to
    // array order and selected Ravi — the male voice — for an assistant whose
    // whole persona is a woman named Anya.
    const realWindowsVoices = [
      voice('Microsoft David - English (United States)', 'en-US'),
      voice('Microsoft Ravi - English (India)', 'en-IN'),
      voice('Microsoft Heera - English (India)', 'en-IN'),
      voice('Microsoft Mark - English (United States)', 'en-US'),
      voice('Microsoft Zira - English (United States)', 'en-US'),
    ]
    expect(pickVoice(realWindowsVoices, 'en-IN')?.name).toBe('Microsoft Heera - English (India)')
  })

  it('picks the female Hindi voice on Windows', () => {
    const installed = [
      voice('Microsoft Hemant - Hindi (India)', 'hi-IN'),
      voice('Microsoft Kalpana - Hindi (India)', 'hi-IN'),
    ]
    expect(pickVoice(installed, 'hi-IN')?.name).toBe('Microsoft Kalpana - Hindi (India)')
  })

  it('picks the female Hindi voice on Apple platforms', () => {
    const installed = [voice('Neel', 'hi-IN'), voice('Lekha', 'hi-IN')]
    expect(pickVoice(installed, 'hi-IN')?.name).toBe('Lekha')
  })

  it('still honours an explicit "female" in the name', () => {
    const installed = [voice('Google UK English Male', 'en-GB'), voice('Google UK English Female', 'en-GB')]
    expect(pickVoice(installed, 'en-GB')?.name).toBe('Google UK English Female')
  })

  it('does not mistake "female" for "male"', () => {
    // The male pattern is word-anchored, so the "male" inside "female" must
    // not score the voice as male.
    expect(pickVoice([voice('Some Female Voice', 'hi-IN')], 'hi-IN')?.name).toBe('Some Female Voice')
  })

  it('uses an unrecognised name rather than refusing to speak', () => {
    // Not recognising a voice costs the wrong gender; refusing it costs
    // silence. The first is much cheaper.
    expect(pickVoice([voice('Google हिन्दी', 'hi-IN')], 'hi-IN')?.name).toBe('Google हिन्दी')
  })

  it('prefers an unknown voice over a known male one', () => {
    const installed = [voice('Microsoft Hemant', 'hi-IN'), voice('Google हिन्दी', 'hi-IN')]
    expect(pickVoice(installed, 'hi-IN')?.name).toBe('Google हिन्दी')
  })

  it('does not match a name token inside a longer word', () => {
    // "mark" must not fire inside "Denmark".
    expect(pickVoice([voice('Denmark Voice', 'hi-IN')], 'hi-IN')?.name).toBe('Denmark Voice')
  })

  it('ranks language above gender', () => {
    // A Hindi line read by an English voice is unintelligible; the wrong
    // gender is merely off-persona.
    const installed = [voice('Lekha', 'en-US'), voice('Microsoft Hemant', 'hi-IN')]
    expect(pickVoice(installed, 'hi-IN')?.name).toBe('Microsoft Hemant')
  })
})

describe('pickVoice — language matching', () => {
  const voices = [
    voice('Microsoft David', 'en-US'),
    voice('Microsoft Heera Female', 'en-IN'),
    voice('Microsoft Ravi', 'en-IN'),
    voice('Google हिन्दी', 'hi-IN'),
  ]

  it('prefers an exact language match labelled female', () => {
    expect(pickVoice(voices, 'en-IN')?.name).toBe('Microsoft Heera Female')
  })

  it('falls back to any exact match when none is labelled female', () => {
    expect(pickVoice(voices, 'hi-IN')?.name).toBe('Google हिन्दी')
  })

  it('falls back to the base language when the exact tag is absent', () => {
    expect(pickVoice([voice('Hindi Voice', 'hi-IN')], 'hi-Deva-IN')?.name).toBe('Hindi Voice')
  })

  it('tolerates underscore-separated tags', () => {
    expect(pickVoice([voice('X', 'hi_IN')], 'hi-IN')?.name).toBe('X')
  })

  it('returns null when the list is empty, letting the platform choose', () => {
    expect(pickVoice([], 'en-IN')).toBeNull()
  })

  it('returns null when no voice shares the base language', () => {
    expect(pickVoice([voice('Only English', 'en-US')], 'hi-IN')).toBeNull()
  })
})

describe('hasVoiceForLang', () => {
  it('is true when a voice shares the base language', () => {
    expect(hasVoiceForLang([voice('Hindi', 'hi-IN')], 'hi-IN')).toBe(true)
  })

  it('is false when none does', () => {
    expect(hasVoiceForLang([voice('English', 'en-US')], 'hi-IN')).toBe(false)
  })

  it('is true for an empty list — unknown, not absent', () => {
    // getVoices() returns [] before `voiceschanged` fires. Treating that as
    // "no Hindi voice" would show a false warning on every cold load.
    expect(hasVoiceForLang([], 'hi-IN')).toBe(true)
  })
})

describe('recognitionErrorMessage', () => {
  // The previous handler was `rec.onerror = () => setVoiceActive(false)`, so
  // a user who denied microphone permission got exactly the same nothing as
  // one who paused mid-sentence.
  it('distinguishes denied permission from silence', () => {
    const denied = recognitionErrorMessage('not-allowed')
    const silence = recognitionErrorMessage('no-speech')
    expect(denied).toMatch(/microphone access is blocked/i)
    expect(silence).toMatch(/didn’t catch that/i)
    expect(denied).not.toBe(silence)
  })

  it('treats service-not-allowed as a permission problem too', () => {
    expect(recognitionErrorMessage('service-not-allowed')).toMatch(/blocked/i)
  })

  it('names hardware and network faults separately', () => {
    expect(recognitionErrorMessage('audio-capture')).toMatch(/no microphone found/i)
    expect(recognitionErrorMessage('network')).toMatch(/internet connection/i)
  })

  it('stays silent for aborted, which is our own stop() call', () => {
    expect(recognitionErrorMessage('aborted')).toBeNull()
  })

  it('names the language when recognition does not support it', () => {
    expect(recognitionErrorMessage('language-not-supported', 'Hindi')).toContain('Hindi')
  })

  it('falls back to an actionable message for unknown codes', () => {
    expect(recognitionErrorMessage('something-new')).toMatch(/type your reply/i)
    expect(recognitionErrorMessage(undefined)).toMatch(/type your reply/i)
  })
})

describe('synthesisErrorMessage', () => {
  it('stays silent for our own cancellations', () => {
    // speechSynthesis.cancel() runs on every new utterance and on unmount.
    expect(synthesisErrorMessage('interrupted')).toBeNull()
    expect(synthesisErrorMessage('canceled')).toBeNull()
  })

  it('explains a missing language voice by name', () => {
    expect(synthesisErrorMessage('language-unavailable', 'Hindi')).toContain('Hindi')
    expect(synthesisErrorMessage('voice-unavailable', 'Hindi')).toContain('Hindi')
  })

  it('explains blocked autoplay', () => {
    expect(synthesisErrorMessage('not-allowed')).toMatch(/blocked audio/i)
  })

  it('falls back for unknown codes without claiming the reply was lost', () => {
    expect(synthesisErrorMessage('mystery')).toMatch(/written above/i)
  })
})

describe('VOICE_LANGS', () => {
  it('carries both directions for each language', () => {
    expect(VOICE_LANGS.en.stt).toBe('en-IN')
    expect(VOICE_LANGS.hi.stt).toBe('hi-IN')
    expect(VOICE_LANGS.hi.tts).toBe('hi-IN')
  })

  it('labels Hindi in its own script for the toggle', () => {
    expect(VOICE_LANGS.hi.nativeLabel).toBe('हिंदी')
  })
})

describe('missingVoiceMessage', () => {
  it('says Anya will fall back to text', () => {
    expect(missingVoiceMessage('Hindi')).toMatch(/text only/i)
  })
})
