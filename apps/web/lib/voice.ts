/**
 * Browser-native voice I/O helpers (Web Speech API) for Anya's wizard.
 *
 * Everything here is pure and browser-agnostic so it can be unit-tested
 * without rendering the 950-line wizard around it. The stateful half lives in
 * `hooks/useVoice.ts`; this file only decides *what* to say, *which* voice to
 * say it with, and *what went wrong*.
 *
 * Three decisions are deliberate and worth reading before editing:
 *
 * * **The speech allowlist is keyed on Unicode categories, not `\w`.**
 *   JavaScript's `\w` is always ASCII `[A-Za-z0-9_]` — the `u` flag does not
 *   change that — so the previous `[^\w\s.,!?'₹%-]` allowlist stripped every
 *   Devanagari character, leaving an empty string that the caller's
 *   `if (!clean) return` turned into total silence. `₹` had been whitelisted
 *   explicitly, so India was in mind; just the currency, not the script.
 *   This is the fourth time this codebase has shipped a character rule
 *   written for one script and applied to every script — see
 *   `apps/api/core/keyword_match.py` and `apps/api/core/validation.py` for
 *   the other three.
 *
 * * **Combining marks (`\p{M}`) are in the allowlist, and that is the whole
 *   point.** Devanagari vowel signs are marks, not letters: `"खाना"` is
 *   ख + ा + न + ा, and `\p{L}` alone keeps only the consonants, yielding
 *   `"खन"` — a real word ("dig"), spoken confidently, meaning something else
 *   entirely. Half-fixing this is worse than not fixing it, because silence
 *   is at least obviously broken.
 *
 * * **The danda `।` is allowed for the same reason `.` is.** It is the
 *   Devanagari full stop, and dropping it while keeping `.` runs every Hindi
 *   sentence together into one flat utterance.
 */

// ── Supported languages ───────────────────────────────────────────────────

/**
 * BCP-47 tags for each language the wizard can listen and speak in.
 *
 * `stt` and `tts` are separate fields even though they currently match: the
 * Web Speech API treats them as unrelated inputs (one selects a recognition
 * model, the other selects an installed system voice), and they are the kind
 * of thing that diverges the moment a third language is added.
 */
export const VOICE_LANGS = {
  en: { stt: 'en-IN', tts: 'en-IN', label: 'English', nativeLabel: 'English' },
  hi: { stt: 'hi-IN', tts: 'hi-IN', label: 'Hindi', nativeLabel: 'हिंदी' },
} as const

export type VoiceLang = keyof typeof VOICE_LANGS

export const DEFAULT_VOICE_LANG: VoiceLang = 'en'

// ── Speech recognition types ──────────────────────────────────────────────

// `SpeechRecognition` is not in TypeScript's DOM lib (it has never been on a
// standards track that ships types), so the shape we actually use is declared
// here rather than pulling in a dependency for four properties.

export type RecognitionInstance = {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onerror: ((e: { error?: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort?: () => void
}

declare global {
  interface Window {
    SpeechRecognition?: new () => RecognitionInstance
    webkitSpeechRecognition?: new () => RecognitionInstance
  }
}

/**
 * The browser's SpeechRecognition constructor, or null where there isn't one.
 *
 * Firefox has never shipped it, and Safari only behind `webkit`. Callers must
 * treat null as "tell the user", not as "return early" — a mic button that
 * does nothing at all on click was the original defect here.
 */
export function getRecognitionCtor(): (new () => RecognitionInstance) | null {
  if (typeof window === 'undefined') return null
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null
}

export function isRecognitionSupported(): boolean {
  return getRecognitionCtor() !== null
}

export function isSynthesisSupported(): boolean {
  return typeof window !== 'undefined' && typeof window.speechSynthesis !== 'undefined'
}

// ── Text → speech-safe text ───────────────────────────────────────────────

/**
 * Characters kept verbatim in an utterance.
 *
 * - `\p{L}` letters, any script.
 * - `\p{M}` combining marks — Devanagari matras live here (see file docstring).
 * - `\p{N}` digits, any script.
 * - `\s` whitespace.
 * - `.,!?'’` sentence punctuation, straight and curly apostrophes (LLM output
 *   uses both).
 * - `।॥` Devanagari danda and double danda: the `.` of Hindi.
 * - `₹%-` kept from the original allowlist — prices are read aloud constantly.
 * - `‌‍` ZWNJ and ZWJ, which are *load-bearing* in Devanagari
 *   conjuncts. `apps/api/core/validation.py` preserves them through backend
 *   normalisation for the same reason; stripping them here would undo that
 *   work one layer later.
 */
const SPEAKABLE_ALLOWLIST = /[^\p{L}\p{M}\p{N}\s.,!?'’।॥₹%‌‍-]/gu

/** At least one letter or digit, in any script. */
const HAS_SPEAKABLE_CONTENT = /[\p{L}\p{N}]/u

/**
 * Strip markdown and unspeakable symbols, leaving text a synthesiser can read.
 *
 * Returns `''` when nothing speakable survives, which callers should treat as
 * "say nothing" — but note that is now a genuinely empty input rather than the
 * old behaviour where any non-Latin script produced it.
 */
export function sanitiseForSpeech(text: string): string {
  if (!text) return ''

  const clean = text
    // Markdown emphasis/heading marks, which otherwise get read as symbols.
    .replace(/[*_~`#]/g, '')
    // `[label](href)` → `label`; nobody wants a URL read aloud.
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(SPEAKABLE_ALLOWLIST, '')
    // Collapse the runs of whitespace the removals above can leave behind.
    .replace(/\s{2,}/g, ' ')
    .trim()

  // Emoji are stripped by the allowlist but ZWJ survives it by design, so an
  // emoji-only string can clean down to a few invisible joiners — non-empty
  // to `if (!clean)`, silent to a synthesiser. Mirrors the backend rule that
  // a value must contain at least one letter or digit to be meaningful.
  if (!HAS_SPEAKABLE_CONTENT.test(clean)) return ''

  return clean
}

// ── Voice selection ───────────────────────────────────────────────────────

/**
 * Anya is a woman, so her voice should be one.
 *
 * **The Web Speech API has no gender field.** `SpeechSynthesisVoice` exposes
 * `name`, `lang`, `default`, `localService` and `voiceURI` — that is the whole
 * interface. The operating system *does* know: on Windows every voice token
 * carries `Attributes\Gender = Female|Male` in the registry (verified — Heera
 * is Female, Ravi is Male). That information is simply dropped at the browser
 * boundary, so matching names is not a shortcut, it is the only lever there is.
 *
 * Matching on the literal word "female" is not enough and was actively wrong.
 * Measured on a real Windows 11 install with Heera *and* Ravi present:
 * neither name contains "female", so the old rule fell through to array order
 * and picked **Ravi, the male voice**, for `en-IN`.
 *
 * These lists are therefore curated per platform. They are a best effort over
 * the voices these platforms are known to ship, not an exhaustive registry —
 * an unrecognised name scores neutral and is still usable, so a device with
 * only voices we don't know about still speaks. That asymmetry is deliberate:
 * the cost of not recognising a voice is the wrong gender, while the cost of
 * refusing it is silence.
 */
const FEMALE_VOICE_TOKENS = [
  // Hindi (India): Windows, Apple, Edge's online natural voice.
  'kalpana', 'lekha', 'swara',
  // Indian English.
  'heera', 'veena', 'neerja',
  // Widely shipped elsewhere, so an en fallback still sounds right.
  'zira', 'hazel', 'susan', 'samantha', 'karen', 'moira', 'tessa', 'fiona',
  'victoria', 'allison', 'ava', 'serena', 'catherine', 'aria', 'jenny',
]

const MALE_VOICE_TOKENS = [
  // Hindi (India).
  'hemant', 'neel', 'madhur',
  // Indian English.
  'ravi', 'rishi', 'prabhat',
  // Widely shipped elsewhere.
  'david', 'mark', 'george', 'daniel', 'alex', 'fred', 'oliver', 'james',
  'richard', 'thomas', 'guy', 'ryan', 'brian',
]

// Word-boundary anchored so "mark" cannot match inside "Denmark".
//
// ⚠️ `\b` is ASCII-only in JavaScript, and that is correct *here* — every
// token above is ASCII, and a name in another script ("Google हिन्दी") simply
// matches nothing and scores neutral, which is the intended "unknown" outcome
// rather than a silent mismatch. Do not "fix" this the way the Devanagari
// boundary bugs elsewhere in this codebase were fixed; the situations are not
// the same.
const FEMALE_NAME_RE = new RegExp(`\\b(${FEMALE_VOICE_TOKENS.join('|')})\\b`, 'i')
const MALE_NAME_RE = new RegExp(`\\b(${MALE_VOICE_TOKENS.join('|')})\\b`, 'i')

export type VoiceGenderGuess = 'female' | 'male' | 'unknown'

/**
 * What the name suggests about a voice's gender.
 *
 * Exported for `app/dev/voice`, the on-device diagnostic — the curated lists
 * are built from platform knowledge rather than measurement, so being able to
 * see what a real phone reports and how it was classified is how they get
 * corrected.
 */
export function voiceGenderGuess(name: string): VoiceGenderGuess {
  const score = genderScore(name)
  return score === 2 ? 'female' : score === 0 ? 'male' : 'unknown'
}

/** 2 = probably female, 1 = unknown, 0 = probably male. */
function genderScore(name: string): number {
  // Checked before the male rule because "female" contains "male". The male
  // pattern is word-anchored so it would not match anyway; the ordering is
  // belt and braces for a rule that is easy to break while editing.
  if (/\bfemale\b|\bwoman\b/i.test(name) || FEMALE_NAME_RE.test(name)) return 2
  if (/\bmale\b|\bman\b/i.test(name) || MALE_NAME_RE.test(name)) return 0
  return 1
}

function baseLang(tag: string): string {
  return tag.split('-')[0]!.toLowerCase()
}

/** 2 = exact tag, 1 = same base language, 0 = unrelated. */
function langScore(voiceLang: string, wantedTag: string): number {
  const v = voiceLang.replace('_', '-').toLowerCase()
  const wanted = wantedTag.replace('_', '-').toLowerCase()
  if (v === wanted) return 2
  if (baseLang(v) === baseLang(wanted)) return 1
  return 0
}

/**
 * Pick the closest installed voice to `langTag`, preferring a female one.
 *
 * Language always outranks gender: an exact-language male voice beats a
 * female voice in the wrong language, because a Hindi line read by an English
 * voice is unintelligible while the wrong gender is merely off-persona.
 * Returns null when nothing shares the base language, meaning "let the
 * platform choose".
 */
export function pickVoice(
  voices: readonly SpeechSynthesisVoice[],
  langTag: string,
): SpeechSynthesisVoice | null {
  let best: SpeechSynthesisVoice | null = null
  let bestScore = 0

  for (const v of voices) {
    const lang = langScore(v.lang, langTag)
    if (lang === 0) continue
    // Language dominates; gender breaks ties within a language tier.
    const score = lang * 10 + genderScore(v.name)
    // Strict `>` keeps the platform's own ordering for genuine ties.
    if (score > bestScore) {
      best = v
      bestScore = score
    }
  }

  return best
}

/**
 * Whether any installed voice can speak `langTag`'s base language.
 *
 * Checked *before* speaking rather than waiting for a `language-unavailable`
 * error, because not every browser fires one — several just stay silent, which
 * is indistinguishable from the bug this module exists to fix. Hindi voices
 * are genuinely absent on a lot of desktop installs, so this is the expected
 * path, not an edge case.
 */
export function hasVoiceForLang(
  voices: readonly SpeechSynthesisVoice[],
  langTag: string,
): boolean {
  if (voices.length === 0) return true // Unknown, not absent — see useVoice.
  const wantedBase = baseLang(langTag)
  return voices.some((v) => baseLang(v.lang.replace('_', '-')) === wantedBase)
}

// ── Error messages ────────────────────────────────────────────────────────

/**
 * A user-facing message for a `SpeechRecognitionErrorEvent.error` code, or
 * null when the condition is not worth surfacing.
 *
 * The API distinguishes six failure modes and the previous handler collapsed
 * all of them into `setVoiceActive(false)` — so denying microphone permission
 * looked exactly like pausing mid-sentence. Null is returned only for
 * `aborted`, which is what our own `stop()` raises.
 */
export function recognitionErrorMessage(code: string | undefined, langLabel?: string): string | null {
  switch (code) {
    case 'aborted':
      // We called stop(), or the user navigated away. Not a failure.
      return null
    case 'not-allowed':
    case 'service-not-allowed':
      return 'Microphone access is blocked. Allow it in your browser’s site settings, then try again.'
    case 'no-speech':
      return 'I didn’t catch that — tap the mic and try again.'
    case 'audio-capture':
      return 'No microphone found. Check that one is connected and try again.'
    case 'network':
      return 'Voice input needs an internet connection.'
    case 'language-not-supported':
      return langLabel
        ? `This browser can’t recognise spoken ${langLabel}. Try switching language, or type instead.`
        : 'This browser can’t recognise that language. Try typing instead.'
    default:
      return 'Voice input didn’t work — you can type your reply instead.'
  }
}

/**
 * A user-facing message for a `SpeechSynthesisErrorEvent.error` code, or null
 * when it is our own cancellation.
 *
 * `interrupted` and `canceled` are raised by the `speechSynthesis.cancel()`
 * calls this feature makes on every new utterance and on unmount, so they are
 * routine control flow rather than something to report.
 */
export function synthesisErrorMessage(code: string | undefined, langLabel?: string): string | null {
  switch (code) {
    case 'interrupted':
    case 'canceled':
      return null
    case 'not-allowed':
      return 'Your browser blocked audio playback. Interact with the page, then try voice again.'
    case 'language-unavailable':
    case 'voice-unavailable':
      return langLabel
        ? `No ${langLabel} voice is installed on this device, so Anya can’t speak ${langLabel} here.`
        : 'No voice is installed for that language on this device.'
    case 'audio-busy':
    case 'audio-hardware':
      return 'Audio output is unavailable right now.'
    default:
      return 'Anya couldn’t speak that reply — it’s written above.'
  }
}

/** Shown when the browser has no SpeechRecognition at all (Firefox). */
export const UNSUPPORTED_RECOGNITION_MESSAGE =
  'Voice input isn’t supported in this browser. Chrome or Edge will work — or just type your reply.'

/** Shown when a language is selected but no system voice can speak it. */
export function missingVoiceMessage(langLabel: string): string {
  return `No ${langLabel} voice is installed on this device, so Anya will reply in text only.`
}
