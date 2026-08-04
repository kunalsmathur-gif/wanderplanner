'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { synthesizeVoice, TtsRequestError } from '@/lib/api'
import {
  DEFAULT_VOICE_LANG,
  SILENT_AUDIO_DATA_URI,
  UNSUPPORTED_RECOGNITION_MESSAGE,
  VOICE_LANGS,
  getRecognitionCtor,
  hasVoiceForLang,
  isSynthesisSupported,
  missingVoiceMessage,
  pickVoice,
  recognitionErrorMessage,
  sanitiseForSpeech,
  synthesisErrorMessage,
  ttsErrorMessage,
  type RecognitionInstance,
  type VoiceLang,
} from '@/lib/voice'

/**
 * Voice conversation state for the wizard: mic in, Anya's replies out.
 *
 * ## Why this is a hook rather than four `useState`s in the component
 *
 * The Web Speech API is entirely event-driven, and every handler it takes is
 * a closure captured at the moment `start()` is called. The previous inline
 * implementation had a single `voiceActive` flag doing two different jobs, and
 * both of the resulting bugs were invisible in the UI:
 *
 * 1. **`onresult` captured a pre-toggle render.** `toggleVoice()` assigned
 *    `rec.onresult = () => handleSubmit(...)` and *then* called
 *    `setVoiceActive(true)`, so the handler held the `handleSubmit` — and
 *    transitively the `sendMessage` — from the render where `voiceActive` was
 *    still `false`. `sendMessage`'s `if (voiceActive) speak(reply)` therefore
 *    read `false` on every voice-driven turn.
 * 2. **`onend` cleared the mode, not just the mic.** Recognition ends the
 *    instant the user stops talking, seconds before the API replies, so even
 *    a fresh read of the flag would have been `false` by then.
 *
 * Either bug alone means Anya never speaks; together they meant the
 * text-to-speech half of this feature had never run in production at all.
 * The fixes are structural rather than a patch: `voiceMode` (the user wants a
 * spoken conversation) is now distinct from `isListening` (the mic is open
 * right now), and every value an event handler needs is read through a ref so
 * it cannot be captured stale.
 *
 * ## Echo
 *
 * The mic is re-armed only from the utterance's own `onend`, never while
 * speech is playing, so an open mic can't transcribe Anya's own voice back
 * into the conversation.
 */

export interface UseVoiceOptions {
  /** Called with a final transcript. Held in a ref, so it is never stale. */
  onTranscript: (text: string) => void
  /** User-facing message — errors and notices both arrive here. */
  onNotice?: (message: string) => void
  /**
   * Gate for re-arming the mic after Anya finishes speaking. The wizard uses
   * this to stop the mic reopening once generation has started.
   */
  canListen?: () => boolean
}

export interface UseVoiceApi {
  /** Whether this browser has SpeechRecognition. False during SSR. */
  supported: boolean
  /** The user has asked for a spoken conversation. Survives each turn. */
  voiceMode: boolean
  /** The mic is open right now. */
  isListening: boolean
  /** Anya is speaking right now. */
  isSpeaking: boolean
  lang: VoiceLang
  setLang: (lang: VoiceLang) => void
  toggleVoiceMode: () => void
  /**
   * Speak a reply if — and only if — voice mode is on. Safe to call always.
   *
   * `sig` should be the `reply_sig` `/wizard-chat` returned alongside this
   * exact `text` — pass it through unmodified so the server voice
   * (Google Chirp 3: HD / Achernar, docs/adr/0001) can verify the text and
   * synthesize it. Omitting `sig` falls back to the browser's own
   * `speechSynthesis`, which should not happen in practice once every
   * caller threads `reply_sig` through; it exists as a defensive path, not
   * a second supported voice.
   */
  speakReply: (text: string, sig?: string | null) => void
  /** Stop any in-flight speech without leaving voice mode. */
  stopSpeaking: () => void
}

export function useVoice(options: UseVoiceOptions): UseVoiceApi {
  const [supported, setSupported] = useState(false)
  const [voiceMode, setVoiceMode] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [lang, setLangState] = useState<VoiceLang>(DEFAULT_VOICE_LANG)

  // Every value an event handler reads goes through a ref. See the docstring:
  // handlers outlive the render that created them, and this feature's original
  // defect was exactly that.
  const optionsRef = useRef(options)
  optionsRef.current = options

  const voiceModeRef = useRef(false)
  const langRef = useRef<VoiceLang>(DEFAULT_VOICE_LANG)
  const recognitionRef = useRef<RecognitionInstance | null>(null)
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null)
  const voicesRef = useRef<readonly SpeechSynthesisVoice[]>([])
  const listeningRef = useRef(false)
  // The one <audio> element server-voiced replies play through. Reused
  // rather than a fresh `new Audio()` per reply — the same "unlock once,
  // reuse forever" trick as `primedRef`/`primeSynthesis` below, and for the
  // same reason: iOS Safari's user-gesture rule doesn't reliably survive a
  // brand-new element created later, without a gesture on the stack.
  const audioRef = useRef<HTMLAudioElement | null>(null)
  // Object URL currently assigned to `audioRef.current.src`, so it can be
  // revoked before the next one replaces it instead of leaking.
  const audioUrlRef = useRef<string | null>(null)
  // Whether the synthesiser has been unlocked by a user gesture (iOS Safari).
  const primedRef = useRef(false)
  // Which language we have already reported as unspeakable, so the warning
  // does not repeat on every turn.
  const warnedLangRef = useRef<VoiceLang | null>(null)

  const notify = useCallback((message: string | null) => {
    if (message) optionsRef.current.onNotice?.(message)
  }, [])

  /**
   * Can we speak `lang` on this device? Warns once if not.
   *
   * Called when the user picks a language rather than only when Anya first
   * tries to reply: choosing हिंदी and finding out three turns later that the
   * device has no Hindi voice is a worse experience than being told up front.
   * Hindi voices are genuinely absent on most desktop installs, so this is the
   * common path, not an edge case.
   */
  const ensureVoiceForLang = useCallback((lang: VoiceLang): boolean => {
    if (!isSynthesisSupported()) return false

    const { tts, label } = VOICE_LANGS[lang]
    // An empty list means voices have not loaded yet, not that none exist —
    // `hasVoiceForLang` returns true for that, and the `voiceschanged` effect
    // re-runs this check once the real list arrives.
    if (hasVoiceForLang(voicesRef.current, tts)) {
      if (warnedLangRef.current === lang) warnedLangRef.current = null
      return true
    }

    if (warnedLangRef.current !== lang) {
      warnedLangRef.current = lang
      notify(missingVoiceMessage(label))
    }
    return false
  }, [notify])

  // ── Capability detection ────────────────────────────────────────────────
  // Deferred to an effect rather than computed inline: `window` does not exist
  // during Next's server render, and initialising this from `typeof window`
  // would make the server and client disagree on whether the mic button is
  // enabled — a hydration mismatch.
  useEffect(() => {
    setSupported(getRecognitionCtor() !== null)
  }, [])

  // ── Voice list ──────────────────────────────────────────────────────────
  // Chrome returns [] from getVoices() until it has loaded them asynchronously
  // and fired `voiceschanged`. Reading it once at speak() time — as the
  // previous code did — meant a cold page load silently fell through to the
  // platform default voice, so the en-IN persona never applied to the first
  // utterance of a session, which is the one that sets the tone.
  useEffect(() => {
    if (!isSynthesisSupported()) return
    const synth = window.speechSynthesis

    const load = () => {
      voicesRef.current = synth.getVoices()
      // Re-judge the selected language now that we know what exists. A choice
      // made before this fired could not be judged at the time.
      if (voicesRef.current.length > 0) ensureVoiceForLang(langRef.current)
    }
    load()
    synth.addEventListener?.('voiceschanged', load)
    return () => synth.removeEventListener?.('voiceschanged', load)
  }, [ensureVoiceForLang])

  // ── Listening ───────────────────────────────────────────────────────────

  const stopListening = useCallback(() => {
    listeningRef.current = false
    setIsListening(false)
    try {
      recognitionRef.current?.stop()
    } catch {
      // stop() throws if recognition was never started. Nothing to undo.
    }
    recognitionRef.current = null
  }, [])

  const startListening = useCallback(() => {
    const Ctor = getRecognitionCtor()
    if (!Ctor) {
      notify(UNSUPPORTED_RECOGNITION_MESSAGE)
      return
    }
    // Starting an already-running recognition throws InvalidStateError.
    if (listeningRef.current) return

    const rec = new Ctor()
    rec.continuous = false
    rec.interimResults = false
    rec.lang = VOICE_LANGS[langRef.current].stt

    rec.onresult = (e) => {
      const transcript = e.results?.[0]?.[0]?.transcript ?? ''
      if (transcript.trim()) optionsRef.current.onTranscript(transcript)
    }
    rec.onerror = (e) => {
      listeningRef.current = false
      setIsListening(false)
      notify(recognitionErrorMessage(e?.error, VOICE_LANGS[langRef.current].label))
    }
    rec.onend = () => {
      // Only the mic closed. Voice mode is the user's choice and outlives it —
      // clearing it here is what stopped Anya ever speaking a reply.
      listeningRef.current = false
      setIsListening(false)
    }

    try {
      rec.start()
    } catch {
      notify('Couldn’t start the microphone. Try again, or type your reply.')
      return
    }
    recognitionRef.current = rec
    listeningRef.current = true
    setIsListening(true)
  }, [notify])

  // ── Speaking ────────────────────────────────────────────────────────────

  const stopSpeaking = useCallback(() => {
    if (isSynthesisSupported()) window.speechSynthesis.cancel()
    utteranceRef.current = null
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current)
      audioUrlRef.current = null
    }
    setIsSpeaking(false)
  }, [])

  /**
   * Unlock both speech paths while a user gesture is still on the stack.
   *
   * iOS Safari only allows `speechSynthesis.speak()` / `<audio>.play()` from
   * inside a user gesture, and Anya's first reply arrives *after* an awaited
   * API call — long past the tap that started voice mode. On iPhone that
   * reads as the feature simply not working, which is the exact symptom this
   * whole milestone was fixing.
   *
   * Speaking a silent utterance, and separately playing a silent `<audio>`
   * element, synchronously inside the toggle handler satisfies the gesture
   * requirement for the rest of the session for both paths. It is a no-op
   * everywhere else: a zero-volume clip costs nothing on desktop.
   *
   * ⚠️ Not verified on a real iPhone — this is defensive, based on a
   * documented WebKit constraint. `app/dev/voice` exists to check it on a
   * device.
   */
  const primeSynthesis = useCallback(() => {
    if (primedRef.current) return
    primedRef.current = true

    if (isSynthesisSupported()) {
      const warmup = new SpeechSynthesisUtterance(' ')
      warmup.volume = 0
      window.speechSynthesis.speak(warmup)
    }

    if (typeof Audio !== 'undefined') {
      const audio = audioRef.current ?? new Audio()
      audioRef.current = audio
      audio.src = SILENT_AUDIO_DATA_URI
      audio.volume = 0
      // Best-effort: autoplay/gesture rules vary by browser, and a real
      // reply later will surface its own error if speech genuinely never
      // works on this device — nothing to recover from here. Wrapped in
      // `Promise.resolve` because `HTMLMediaElement.play()` isn't
      // guaranteed to return a promise (jsdom's test-environment stub
      // returns `undefined`).
      Promise.resolve(audio.play()).catch(() => {})
    }
  }, [])

  /** Re-open the mic after a turn, if the caller still wants one. */
  const rearm = useCallback(() => {
    if (!voiceModeRef.current) return
    if (optionsRef.current.canListen && !optionsRef.current.canListen()) return
    startListening()
  }, [startListening])

  /**
   * Speaks `text` with Anya's real, server-synthesized voice (the whole
   * point of docs/adr/0001-anya-voice-provider.md: the same voice on every
   * device, not whatever `speechSynthesis` happens to expose locally).
   *
   * Any failure here — provider off, budget spent, bad/expired signature,
   * a transient provider error — surfaces a text notice and nothing else.
   * It deliberately never falls back to `window.speechSynthesis`: that
   * fallback is the exact "different Anya on every device" bug this
   * project exists to retire, so resurrecting it on error would silently
   * undo the fix for the one message a user might most want spoken well.
   */
  const speakViaServer = useCallback(
    async (text: string, sig: string) => {
      const { tts } = VOICE_LANGS[langRef.current]
      try {
        const blob = await synthesizeVoice(text, tts, sig)
        const url = URL.createObjectURL(blob)
        const audio = audioRef.current ?? new Audio()
        audioRef.current = audio

        if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
        audioUrlRef.current = url

        audio.src = url
        audio.volume = 1.0
        audio.onplay = () => setIsSpeaking(true)
        audio.onended = () => {
          setIsSpeaking(false)
          // Re-arm here and nowhere else: the mic must never be open while
          // audio is playing, or it transcribes Anya back into the chat.
          rearm()
        }
        audio.onerror = () => {
          setIsSpeaking(false)
          notify(ttsErrorMessage('tts_unavailable'))
          rearm()
        }
        await Promise.resolve(audio.play())
      } catch (e) {
        setIsSpeaking(false)
        const code = e instanceof TtsRequestError ? e.code : 'unknown'
        notify(ttsErrorMessage(code))
        rearm()
      }
    },
    [notify, rearm],
  )

  const speakReply = useCallback(
    (text: string, sig?: string | null) => {
      // Read through the ref, not a captured `voiceMode` — this line is the
      // one the original stale closure got wrong.
      if (!voiceModeRef.current) return

      const clean = sanitiseForSpeech(text)
      if (!clean) { rearm(); return }

      // The server voice is the product (see docstring above) — this is the
      // only path taken once every caller threads `reply_sig` through.
      if (sig) {
        void speakViaServer(clean, sig)
        return
      }

      // Defensive fallback for the should-not-happen case of no signature
      // (e.g. signing itself failed server-side) — not a second supported
      // voice. Everything below is unchanged from before server-side TTS.
      if (!isSynthesisSupported()) { rearm(); return }

      const { tts, label } = VOICE_LANGS[langRef.current]

      // Re-checked here as well as at selection because several browsers stay
      // silent instead of firing `language-unavailable`, and silence is
      // indistinguishable from the bug this hook exists to fix. The notice is
      // deduplicated, so an already-warned language does not warn again.
      if (!ensureVoiceForLang(langRef.current)) {
        rearm()
        return
      }

      window.speechSynthesis.cancel()

      const utterance = new SpeechSynthesisUtterance(clean)
      utterance.lang = tts
      const preferred = pickVoice(voicesRef.current, tts)
      if (preferred) utterance.voice = preferred
      utterance.rate = 1.05
      utterance.pitch = 1.15
      utterance.volume = 1.0
      utterance.onstart = () => setIsSpeaking(true)
      utterance.onend = () => {
        setIsSpeaking(false)
        // Re-arm here and nowhere else: the mic must never be open while
        // audio is playing, or it transcribes Anya back into the chat.
        rearm()
      }
      utterance.onerror = (e) => {
        setIsSpeaking(false)
        notify(synthesisErrorMessage((e as { error?: string })?.error, label))
        rearm()
      }

      // Held in a ref because Chrome drops utterance events if the object is
      // garbage collected mid-speech.
      utteranceRef.current = utterance
      window.speechSynthesis.speak(utterance)
    },
    [ensureVoiceForLang, notify, rearm, speakViaServer],
  )

  // ── Mode + language ─────────────────────────────────────────────────────

  const toggleVoiceMode = useCallback(() => {
    if (voiceModeRef.current) {
      voiceModeRef.current = false
      setVoiceMode(false)
      stopListening()
      stopSpeaking()
      return
    }

    // Firefox has never shipped SpeechRecognition. The button used to be
    // rendered unconditionally and `return` on a missing constructor, so a
    // click did nothing whatsoever — no state change, no message.
    if (getRecognitionCtor() === null) {
      notify(UNSUPPORTED_RECOGNITION_MESSAGE)
      return
    }

    // Must happen here, synchronously, while the click that called us is
    // still the active gesture — not later from the reply handler.
    primeSynthesis()

    voiceModeRef.current = true
    setVoiceMode(true)
    startListening()
  }, [notify, primeSynthesis, startListening, stopListening, stopSpeaking])

  const setLang = useCallback(
    (next: VoiceLang) => {
      if (next === langRef.current) return
      langRef.current = next
      setLangState(next)

      // Tell the user now, not on Anya's first reply. The dedupe is cleared
      // first so that an *explicit* selection always answers — staying quiet
      // when someone deliberately re-picks हिंदी reads as "it works now".
      // Automatic re-checks (speakReply, voiceschanged) still warn only once.
      warnedLangRef.current = null
      ensureVoiceForLang(next)

      // `lang` is read by the recognition engine at start() time only, so a
      // live session has to be restarted to pick up the change.
      if (voiceModeRef.current) {
        stopSpeaking()
        if (listeningRef.current) {
          stopListening()
          startListening()
        }
      }
    },
    [ensureVoiceForLang, startListening, stopListening, stopSpeaking],
  )

  // ── Unmount ─────────────────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      voiceModeRef.current = false
      try {
        recognitionRef.current?.stop()
      } catch {
        // Already stopped.
      }
      recognitionRef.current = null
      if (isSynthesisSupported()) window.speechSynthesis.cancel()
      if (audioRef.current) audioRef.current.pause()
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
    }
  }, [])

  return {
    supported,
    voiceMode,
    isListening,
    isSpeaking,
    lang,
    setLang,
    toggleVoiceMode,
    speakReply,
    stopSpeaking,
  }
}
