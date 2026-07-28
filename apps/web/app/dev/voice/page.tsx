'use client'

/**
 * On-device Web Speech API diagnostic. Open `/dev/voice` on a real phone.
 *
 * The curated female/male voice lists in `lib/voice.ts` are built from what
 * Windows, Apple and Edge are *known* to ship — platform knowledge, not
 * measurement. Android is the weak spot: Google's TTS voices arrive named
 * "Google हिन्दी" with no personal name and no gender token, so nothing in
 * those lists can match and selection falls through to the platform default.
 *
 * This page exists to replace that guesswork with a real report. It also
 * tests the thing that unit tests cannot: whether iOS Safari lets us speak
 * *outside* a user gesture, which is how Anya's replies actually arrive.
 */

import { useCallback, useEffect, useState } from 'react'
import {
  VOICE_LANGS,
  isRecognitionSupported,
  isSynthesisSupported,
  pickVoice,
  voiceGenderGuess,
  type VoiceLang,
} from '@/lib/voice'

const SAMPLE: Record<VoiceLang, string> = {
  en: 'Goa is a wonderful choice. When would you like to travel?',
  hi: 'गोवा बहुत सुंदर है। आप कब जाना चाहेंगे?',
}

type GestureResult = 'untested' | 'testing' | 'spoke' | 'silent'

export default function VoiceCheckPage() {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  const [caps, setCaps] = useState({ recognition: false, synthesis: false, ua: '' })
  const [gesture, setGesture] = useState<GestureResult>('untested')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    setCaps({
      recognition: isRecognitionSupported(),
      synthesis: isSynthesisSupported(),
      ua: navigator.userAgent,
    })
    if (!isSynthesisSupported()) return

    const synth = window.speechSynthesis
    const load = () => setVoices(synth.getVoices())
    load()
    synth.addEventListener?.('voiceschanged', load)
    return () => synth.removeEventListener?.('voiceschanged', load)
  }, [])

  const speak = useCallback((lang: VoiceLang) => {
    const { tts } = VOICE_LANGS[lang]
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(SAMPLE[lang])
    u.lang = tts
    const chosen = pickVoice(voices, tts)
    if (chosen) u.voice = chosen
    u.rate = 1.05
    u.pitch = 1.15
    window.speechSynthesis.speak(u)
  }, [voices])

  /**
   * The iOS question, and the only one a unit test cannot answer.
   *
   * Anya's reply is spoken after an awaited API call, so the gesture that
   * started voice mode is long gone. This reproduces that exact shape: wait a
   * second, then speak with no gesture on the stack. If `onstart` never
   * fires, iOS is blocking it and the priming utterance in `useVoice` is
   * doing real work.
   */
  const testGesture = useCallback(() => {
    setGesture('testing')
    window.speechSynthesis.cancel()
    let started = false
    setTimeout(() => {
      const u = new SpeechSynthesisUtterance('Testing delayed speech.')
      u.lang = VOICE_LANGS.en.tts
      u.onstart = () => { started = true; setGesture('spoke') }
      window.speechSynthesis.speak(u)
      // Generous: some platforms take a moment to start.
      setTimeout(() => { if (!started) setGesture('silent') }, 3000)
    }, 1000)
  }, [])

  const report = [
    `userAgent: ${caps.ua}`,
    `SpeechRecognition: ${caps.recognition}`,
    `speechSynthesis: ${caps.synthesis}`,
    `delayed speech (no gesture): ${gesture}`,
    `voices: ${voices.length}`,
    ...voices.map(
      (v) => `  - "${v.name}" | ${v.lang} | ${voiceGenderGuess(v.name)} | local=${v.localService} | uri=${v.voiceURI}`,
    ),
    ...(Object.keys(VOICE_LANGS) as VoiceLang[]).map((code) => {
      const chosen = pickVoice(voices, VOICE_LANGS[code].tts)
      return `selected for ${VOICE_LANGS[code].tts}: ${chosen ? `"${chosen.name}" (${voiceGenderGuess(chosen.name)})` : 'none — platform default'}`
    }),
  ].join('\n')

  return (
    <main className="mx-auto max-w-2xl px-4 py-8 text-[var(--_fg)]">
      <h1 className="mb-1 text-xl font-bold">Voice capability check</h1>
      <p className="mb-6 text-sm text-[var(--_muted-fg)]">
        Open this on a real device. Everything below is read from that device.
      </p>

      <section className="mb-6 rounded-xl border border-[var(--_border)] p-4">
        <h2 className="mb-2 text-sm font-bold">Capabilities</h2>
        <dl className="space-y-1 text-sm">
          <Row label="Speech recognition (mic in)" value={caps.recognition ? 'supported' : 'NOT supported'} bad={!caps.recognition} />
          <Row label="Speech synthesis (Anya out)" value={caps.synthesis ? 'supported' : 'NOT supported'} bad={!caps.synthesis} />
          <Row label="Voices reported" value={String(voices.length)} bad={voices.length === 0} />
        </dl>
      </section>

      <section className="mb-6 rounded-xl border border-[var(--_border)] p-4">
        <h2 className="mb-2 text-sm font-bold">What Anya would use</h2>
        {(Object.keys(VOICE_LANGS) as VoiceLang[]).map((code) => {
          const { tts, label } = VOICE_LANGS[code]
          const chosen = pickVoice(voices, tts)
          const guess = chosen ? voiceGenderGuess(chosen.name) : null
          return (
            <div key={code} className="mb-3 last:mb-0">
              <p className="text-sm font-semibold">{label} ({tts})</p>
              <p className="text-sm text-[var(--_muted-fg)]">
                {chosen
                  ? <>Selected <strong>{chosen.name}</strong> — classified <strong>{guess}</strong>
                      {guess === 'unknown' && ' (name not in the curated list, so this is the platform default order)'}</>
                  : 'No voice for this language — Anya falls back to text only.'}
              </p>
              <button
                type="button"
                onClick={() => speak(code)}
                disabled={!chosen}
                className="mt-1 rounded-lg border border-[var(--_border)] px-3 py-1.5 text-sm disabled:opacity-40"
              >
                Speak {label} sample
              </button>
            </div>
          )
        })}
      </section>

      <section className="mb-6 rounded-xl border border-[var(--_border)] p-4">
        <h2 className="mb-1 text-sm font-bold">Delayed speech (the iOS question)</h2>
        <p className="mb-2 text-sm text-[var(--_muted-fg)]">
          Anya speaks after an API call, so the tap that started voice mode is
          long gone. This waits a second, then speaks with no gesture active.
          If it stays silent, iOS is blocking it.
        </p>
        <button
          type="button"
          onClick={testGesture}
          className="rounded-lg border border-[var(--_border)] px-3 py-1.5 text-sm"
        >
          Run delayed-speech test
        </button>
        <p className="mt-2 text-sm">
          Result:{' '}
          <strong>
            {gesture === 'untested' && 'not run yet'}
            {gesture === 'testing' && 'waiting…'}
            {gesture === 'spoke' && 'spoke — no gesture restriction here'}
            {gesture === 'silent' && 'SILENT — gesture restriction applies'}
          </strong>
        </p>
      </section>

      <section className="rounded-xl border border-[var(--_border)] p-4">
        <h2 className="mb-2 text-sm font-bold">Report</h2>
        <button
          type="button"
          onClick={() => {
            navigator.clipboard?.writeText(report).then(
              () => { setCopied(true); setTimeout(() => setCopied(false), 2000) },
              () => setCopied(false),
            )
          }}
          className="mb-2 rounded-lg border border-[var(--_border)] px-3 py-1.5 text-sm"
        >
          {copied ? 'Copied' : 'Copy report'}
        </button>
        <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-[var(--_bg)] p-3 text-xs">
          {report}
        </pre>
      </section>
    </main>
  )
}

function Row({ label, value, bad }: { label: string; value: string; bad: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-[var(--_muted-fg)]">{label}</dt>
      <dd className={bad ? 'font-semibold text-[var(--color-destructive)]' : 'font-semibold'}>{value}</dd>
    </div>
  )
}
