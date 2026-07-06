'use client'

import { useEffect, useRef, useState } from 'react'
import { Mic, MicOff, Send, Plane, X, CheckCircle2, Loader2 } from 'lucide-react'
import { useAppStore } from '@/store/appStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useWizardChatStore } from '@/store/wizardChatStore'
import { wizardChat } from '@/lib/api'
import { streamItinerary } from '@/lib/api'
import type { TripConfig } from '@/types'
import { WanderplanLogo } from '@/components/common/WanderplanLogo'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  chips?: string[]
  config_patch?: Record<string, unknown>  // stored so backend can replay real patches in history
}

type Phase = 'chatting' | 'generating' | 'done'

interface ItineraryProgress {
  message: string
  step: number
  total: number
}

let _msgId = 0
const nextId = () => `llm-msg-${++_msgId}`

// ── Voice helpers ─────────────────────────────────────────────────────────────

type RecognitionInstance = {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onerror: ((e: { error?: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}

declare global {
  interface Window {
    SpeechRecognition?: new () => RecognitionInstance
    webkitSpeechRecognition?: new () => RecognitionInstance
  }
}

// ── Required-field progress display ──────────────────────────────────────────

const REQUIRED_LABELS: { key: string; label: string }[] = [
  { key: 'purpose',     label: 'Purpose'     },
  { key: 'destination', label: 'Destination' },
  { key: 'dates',       label: 'Dates'       },
  { key: 'budget',      label: 'Budget'      },
  { key: 'group',       label: 'Group'       },
  { key: 'pace',        label: 'Pace'        },
]

// Theme chips (Culture, Food, Adventure, ...) map to a multi-value array
// field, so unlike every other chip group (purpose, pace, etc.) the user
// should be able to pick several before submitting.
const THEME_CHIP_KEYWORDS = [
  'culture', 'nature', 'food', 'adventure', 'shopping', 'photography',
  'nightlife', 'sports', 'wellness', 'religious', 'vegetarian',
]

function _isThemeChipGroup(chips: string[]): boolean {
  return chips.length >= 2 && chips.every((c) => THEME_CHIP_KEYWORDS.some((k) => c.toLowerCase().includes(k)))
}

function _isFieldFilled(key: string, config: Partial<TripConfig>): boolean {
  switch (key) {
    case 'purpose':     return Boolean(config.purpose)
    case 'destination': {
      const mode = config.destination_mode ?? 'fixed'
      if (mode === 'exploring') return true
      if (mode === 'country') return Boolean(config.destination_country)
      return Boolean(config.destination?.city)
    }
    case 'dates': {
      const d = config.dates
      if (!d) return false
      return (Boolean(d.start && d.end)) || Boolean(d.flexible && (d as { duration_days?: number }).duration_days)
    }
    case 'budget':      return (config.budget?.amount ?? 0) > 0
    case 'group':       return (config.group?.adults ?? 0) >= 1
    case 'pace':        return Boolean(config.pace)
    default:            return false
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

export function LLMWizard() {
  const closeWizard       = useAppStore((s) => s.closeWizard)
  const wizardPreload     = useAppStore((s) => s.wizardPreload)
  const clearPreload      = useAppStore((s) => s.clearWizardPreload)
  const setDays           = useItineraryStore((s) => s.setDays)
  const updateConfig      = useTripConfigStore((s) => s.updateConfig)
  const wizardReset       = useWizardChatStore((s) => s.reset)

  const [messages, setMessages]       = useState<Message[]>([])
  const [input, setInput]             = useState('')
  const [phase, setPhase]             = useState<Phase>('chatting')
  const [isSending, setIsSending]     = useState(false)
  const [partialConfig, setPartialConfig] = useState<Partial<TripConfig>>({})
  const [summary, setSummary]         = useState<string | null>(null)
  const [progress, setProgress]       = useState<ItineraryProgress>({ message: '', step: 0, total: 6 })
  const [error, setError]             = useState('')
  const [voiceActive, setVoiceActive] = useState(false)
  const [isSpeaking, setIsSpeaking]   = useState(false)
  // Per-message selection set, only used for multi-select theme chip groups
  const [themeSelections, setThemeSelections] = useState<Record<string, Set<string>>>({})

  // Always-current ref so sendMessage never reads stale partialConfig
  const partialConfigRef = useRef<Partial<TripConfig>>({})
  partialConfigRef.current = partialConfig

  const messagesEndRef  = useRef<HTMLDivElement>(null)
  const inputRef        = useRef<HTMLInputElement>(null)
  const recognitionRef  = useRef<RecognitionInstance | null>(null)
  const synthRef        = useRef<SpeechSynthesisUtterance | null>(null)
  const cancelStreamRef = useRef<(() => void) | null>(null)

  // ── Bootstrap first Anya message ───────────────────────────────────────────

  useEffect(() => {
    const preload = wizardPreload
    const preloadLabel = preload ? `${preload.city}, ${preload.country}` : undefined

    // Pre-fill destination in config if preloaded
    if (preload) {
      const patch: Partial<TripConfig> = {
        destination: { city: preload.city, country: preload.country, lat: 0, lon: 0 },
        destination_mode: 'fixed',
        dates: preload.days
          ? { start: null, end: null, flexible: true, duration_days: preload.days }
          : { start: null, end: null, flexible: false },
      }
      setPartialConfig(patch)
    }

    // Kick off with a "user is here" seed message so the LLM greets naturally
    const seedContent = preloadLabel
      ? `I want to plan a trip to ${preloadLabel}${preload?.days ? ` for ${preload.days} days` : ''}.`
      : '__START__'

    sendMessage(seedContent, [], preloadLabel)
    clearPreload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Auto-scroll ────────────────────────────────────────────────────────────

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Auto-focus input ───────────────────────────────────────────────────────

  useEffect(() => {
    if (phase === 'chatting' && !isSending) {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [phase, isSending])

  // ── Cleanup on unmount ─────────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      cancelStreamRef.current?.()
      window.speechSynthesis?.cancel()
    }
  }, [])

  // ── Helpers ────────────────────────────────────────────────────────────────

  function addMessage(msg: Omit<Message, 'id'>) {
    setMessages((prev) => [...prev, { ...msg, id: nextId() }])
  }

  function speak(text: string) {
    if (typeof window === 'undefined' || !window.speechSynthesis) return
    window.speechSynthesis.cancel()

    const clean = text
      .replace(/[*_~`#]/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/[^\w\s.,!?'₹%-]/g, '')
      .trim()
    if (!clean) return

    const utterance = new SpeechSynthesisUtterance(clean)
    utterance.lang = 'en-IN'
    const voices = window.speechSynthesis.getVoices()
    const preferred =
      voices.find((v) => v.lang.includes('en-IN') && v.name.toLowerCase().includes('female')) ||
      voices.find((v) => v.lang.startsWith('en') && v.name.toLowerCase().includes('female')) ||
      voices.find((v) => v.lang.includes('en-IN'))
    if (preferred) utterance.voice = preferred
    utterance.rate = 1.05
    utterance.pitch = 1.15
    utterance.volume = 1.0
    utterance.onstart = () => setIsSpeaking(true)
    utterance.onend   = () => setIsSpeaking(false)
    utterance.onerror = () => setIsSpeaking(false)
    synthRef.current = utterance
    window.speechSynthesis.speak(utterance)
  }

  // ── Send a message to Anya ─────────────────────────────────────────────────

  async function sendMessage(
    text: string,
    currentMessages: Message[] = messages,
    preloadLabel?: string,
  ) {
    const isBootstrap = text === '__START__'
    const displayText = isBootstrap ? '' : text

    const nextMessages: Message[] = isBootstrap
      ? currentMessages
      : [...currentMessages, { id: nextId(), role: 'user', content: displayText }]

    if (!isBootstrap) setMessages(nextMessages)
    setIsSending(true)
    setError('')

    // Build history for the API (exclude bootstrap marker)
    // Include config_patch on assistant turns so backend can reconstruct real extraction history
    const history = nextMessages
      .filter((m) => m.content !== '__START__')
      .map((m) => ({
        role: m.role === 'user' ? 'user' : 'assistant',
        content: m.content,
        ...(m.role === 'assistant' && m.config_patch ? { config_patch: m.config_patch } : {}),
      }))

    // Include the seed text for preload context even on bootstrap
    if (isBootstrap && preloadLabel) {
      history.push({ role: 'user', content: `I want to plan a trip to ${preloadLabel}.` })
    }

    try {
      const res = await wizardChat(
        history,
        partialConfigRef.current,   // always-current, avoids stale closure
        preloadLabel ?? (wizardPreload ? `${wizardPreload.city}, ${wizardPreload.country}` : undefined),
      )

      // Merge config_patch into partialConfig
      setPartialConfig((prev) => {
        const merged = { ...prev }
        // Apply any LLM-extracted patches
        if (res.config_patch && Object.keys(res.config_patch).length > 0) {
          for (const [k, v] of Object.entries(res.config_patch)) {
            if (typeof v === 'object' && v !== null && !Array.isArray(v) && typeof merged[k as keyof TripConfig] === 'object') {
              merged[k as keyof TripConfig] = { ...(merged[k as keyof TripConfig] as object), ...v } as never
            } else {
              merged[k as keyof TripConfig] = v as never
            }
          }
        }
        // Coerce group.kids from plain integers to KidAge objects (LLM may emit [3, 6])
        const g = merged.group as Record<string, unknown> | undefined
        if (g && Array.isArray(g.kids)) {
          g.kids = (g.kids as unknown[]).map((k) =>
            typeof k === 'number' ? { age: k } : k
          )
        }
        // Track that the "anything else?" checkpoint has been shown
        // once all 6 fields are filled, so the LLM doesn't re-ask next turn
        // Use the same logic as the tab indicators so _checkpoint_asked is only set
        // when all 6 fields pass the exact same checks shown in the UI
        const allFilled = REQUIRED_LABELS.every(({ key }) => _isFieldFilled(key, merged))
        if (allFilled && !(merged as Record<string, unknown>)._checkpoint_asked) {
          (merged as Record<string, unknown>)._checkpoint_asked = true
        }
        return merged
      })

      const assistantMsg: Message = {
        id: nextId(),
        role: 'assistant',
        content: res.reply,
        chips: res.chips.length > 0 ? res.chips : undefined,
        config_patch: Object.keys(res.config_patch ?? {}).length > 0 ? res.config_patch : undefined,
      }
      setMessages([...nextMessages, assistantMsg])

      if (voiceActive) speak(res.reply)

      if (res.ready_to_generate) {
        setSummary(res.summary)
        // Auto-trigger generation after a short delay so the user sees Anya's final message
        setTimeout(() => {
          handleGenerate()
        }, 1200)
      }
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string }; status?: number } }
      const detail = axiosErr?.response?.data?.detail
      const status = axiosErr?.response?.status
      if (status === 429) {
        setError('Too many requests — please wait a moment and try again.')
      } else if (detail) {
        setError(`Error: ${detail}`)
      } else {
        setError('Connection error — please try again.')
      }
      console.error('[LLMWizard] sendMessage error:', err)
    } finally {
      setIsSending(false)
    }
  }

  // ── User submits a message ─────────────────────────────────────────────────

  async function handleSubmit(text?: string) {
    const value = (text ?? input).trim()
    if (!value || isSending || phase !== 'chatting') return
    setInput('')
    await sendMessage(value)
  }

  // ── Generate itinerary ─────────────────────────────────────────────────────

  function handleGenerate() {
    // Use ref to avoid stale closure (called from setTimeout or button click)
    updateConfig(partialConfigRef.current as Partial<TripConfig>)

    // Build a full TripConfig from the partialConfig + store defaults
    const fullConfig = useTripConfigStore.getState().config

    setPhase('generating')
    setProgress({ message: 'Starting up…', step: 0, total: 6 })
    wizardReset()

    cancelStreamRef.current = streamItinerary(
      fullConfig,
      (msg, step, total) => setProgress({ message: msg, step, total }),
      (result) => {
        setDays(result.days, result.alignment_score, result.expense_breakdown)
        setPhase('done')
        closeWizard()
      },
      (code, message, _retryable) => {
        setError(`Generation failed: ${message} (${code})`)
        setPhase('chatting')
      },
    )
  }

  // ── Voice input ────────────────────────────────────────────────────────────

  function toggleVoice() {
    if (voiceActive) {
      recognitionRef.current?.stop()
      setVoiceActive(false)
      window.speechSynthesis?.cancel()
      setIsSpeaking(false)
      return
    }

    const Ctor = window.SpeechRecognition ?? window.webkitSpeechRecognition
    if (!Ctor) return

    const rec = new Ctor()
    rec.continuous = false
    rec.interimResults = false
    rec.lang = 'en-IN'
    rec.onresult = (e) => {
      const transcript = e.results[0][0].transcript
      setInput(transcript)
      handleSubmit(transcript)
    }
    rec.onerror = () => setVoiceActive(false)
    rec.onend = () => setVoiceActive(false)
    rec.start()
    recognitionRef.current = rec
    setVoiceActive(true)
  }

  // ── Filled fields count for progress bar ──────────────────────────────────

  const filledCount = REQUIRED_LABELS.filter(({ key }) => _isFieldFilled(key, partialConfig)).length
  const progressPct = Math.round((filledCount / REQUIRED_LABELS.length) * 100)
  // Only show the "Generate" card once the server explicitly confirms
  // ready_to_generate (reflected via `summary`). Using "all required fields
  // filled" here was wrong: it hid the text input as soon as the 6 required
  // fields were done, even while Anya was still asking optional follow-up
  // questions (e.g. departure city) — leaving the user with no way to reply.
  const readyToGenerate = summary !== null

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Anya — AI Trip Planner"
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 backdrop-blur-sm sm:items-center"
    >
      <div className="flex w-full max-h-screen flex-col overflow-hidden bg-[var(--_card)] sm:mx-4 sm:max-h-[90vh] sm:max-w-lg sm:rounded-2xl rounded-t-2xl shadow-2xl">

        {/* ── Header ──────────────────────────────────────────────────── */}
        <div className="flex shrink-0 items-center justify-between bg-[var(--_primary)] px-5 py-4 text-white">
          <div className="flex items-center gap-3">
            <WanderplanLogo size="sm" inverted />
            <div>
              <p className="text-sm font-bold leading-tight">Anya</p>
              <p className="text-xs text-white/70">AI travel concierge</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={toggleVoice}
              aria-label={voiceActive ? 'Stop voice mode' : 'Start voice mode'}
              className={[
                'flex h-9 w-9 items-center justify-center rounded-full transition-colors',
                voiceActive
                  ? 'bg-white text-[var(--_primary)] animate-pulse'
                  : 'bg-white/20 text-white hover:bg-white/30',
              ].join(' ')}
            >
              {voiceActive ? <MicOff size={16} /> : <Mic size={16} />}
            </button>
            <button
              type="button"
              onClick={() => { cancelStreamRef.current?.(); closeWizard() }}
              aria-label="Close"
              className="flex h-9 w-9 items-center justify-center rounded-full bg-white/20 text-white hover:bg-white/30"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* ── Progress bar ────────────────────────────────────────────── */}
        <div className="relative h-1 w-full shrink-0 overflow-hidden bg-[var(--_primary)]/20">
          <div
            className="h-full rounded-r-full bg-gradient-to-r from-[var(--_primary)] to-sky-300 transition-all duration-500"
            style={{ width: `${progressPct}%` }}
          />
        </div>

        {/* ── Field pills ─────────────────────────────────────────────── */}
        <div className="flex shrink-0 gap-1.5 overflow-x-auto px-4 py-2 scrollbar-none">
          {REQUIRED_LABELS.map(({ key, label }) => {
            const filled = _isFieldFilled(key, partialConfig)
            return (
              <span
                key={key}
                className={[
                  'flex shrink-0 items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-semibold transition-colors',
                  filled
                    ? 'bg-[var(--_primary)]/15 text-[var(--_primary)]'
                    : 'bg-[var(--_muted)] text-[var(--_muted-fg)]',
                ].join(' ')}
              >
                {filled && <CheckCircle2 size={10} />}
                {label}
              </span>
            )
          })}
        </div>

        {/* ── Messages ────────────────────────────────────────────────── */}
        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
          {messages.map((msg) => (
            <div key={msg.id}>
              {msg.role === 'assistant' ? (
                <div className="flex items-start gap-2">
                  {/* Anya avatar */}
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--_primary)]">
                    <span className="text-sm">✈</span>
                  </div>
                  <div className="max-w-[85%] space-y-2">
                    <div className="rounded-2xl rounded-bl-sm bg-[var(--_muted)] px-4 py-2.5 text-sm leading-relaxed text-[var(--_fg)]">
                      {msg.content}
                    </div>
                    {/* Chips */}
                    {msg.chips && msg.chips.length > 0 && (() => {
                      const visibleChips = msg.chips.filter((chip) => !/generate/i.test(chip))
                      const isThemeGroup = _isThemeChipGroup(visibleChips)
                      const selected = themeSelections[msg.id] ?? new Set<string>()

                      function toggleTheme(chip: string) {
                        setThemeSelections((prev) => {
                          const next = new Set(prev[msg.id] ?? [])
                          if (next.has(chip)) next.delete(chip)
                          else next.add(chip)
                          return { ...prev, [msg.id]: next }
                        })
                      }

                      return (
                        <div className="flex flex-wrap items-center gap-1.5">
                          {visibleChips.map((chip) => {
                            const isSelected = isThemeGroup && selected.has(chip)
                            return (
                              <button
                                key={chip}
                                type="button"
                                onClick={() => (isThemeGroup ? toggleTheme(chip) : handleSubmit(chip))}
                                disabled={isSending || phase !== 'chatting'}
                                className={[
                                  'rounded-full border border-[var(--_primary)] px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50',
                                  isSelected
                                    ? 'bg-[var(--_primary)] text-white'
                                    : 'text-[var(--_primary)] hover:bg-[var(--_primary)] hover:text-white',
                                ].join(' ')}
                              >
                                {chip}
                              </button>
                            )
                          })}
                          {isThemeGroup && selected.size > 0 && (
                            <button
                              type="button"
                              onClick={() => handleSubmit(Array.from(selected).join(', '))}
                              disabled={isSending || phase !== 'chatting'}
                              className="rounded-full bg-[var(--_primary)] px-3 py-1 text-xs font-semibold text-white transition-colors hover:opacity-90 disabled:opacity-50"
                            >
                              Continue ✓
                            </button>
                          )}
                        </div>
                      )
                    })()}
                  </div>
                </div>
              ) : (
                <div className="flex justify-end">
                  <div className="max-w-[75%] rounded-2xl rounded-br-sm bg-[var(--_primary)] px-4 py-2.5 text-sm leading-relaxed text-white">
                    {msg.content}
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Typing indicator */}
          {isSending && (
            <div className="flex items-start gap-2">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--_primary)]">
                <span className="text-sm">✈</span>
              </div>
              <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm bg-[var(--_muted)] px-4 py-3">
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    className="block h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--_muted-fg)]"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Generating progress */}
          {phase === 'generating' && (
            <div className="flex items-center gap-3 rounded-2xl border border-[var(--_border)] bg-[var(--_card)] px-4 py-3">
              <Loader2 size={16} className="shrink-0 animate-spin text-[var(--_primary)]" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-[var(--_fg)]">{progress.message || 'Generating your itinerary…'}</p>
                <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-[var(--_muted)]">
                  <div
                    className="h-full rounded-full bg-[var(--_primary)] transition-all duration-500"
                    style={{ width: `${progress.total > 0 ? Math.round((progress.step / progress.total) * 100) : 10}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 rounded-xl bg-red-50 px-3 py-2 dark:bg-red-950/40">
              <p className="flex-1 text-xs text-red-600 dark:text-red-400">{error}</p>
              <button
                type="button"
                onClick={() => {
                  const lastUser = [...messages].reverse().find((m) => m.role === 'user')
                  if (lastUser) {
                    setMessages((prev) => prev.slice(0, -1)) // remove last user msg to re-send
                    setError('')
                    sendMessage(lastUser.content, messages.slice(0, -1))
                  } else {
                    setError('')
                  }
                }}
                className="shrink-0 rounded-lg bg-red-100 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-200 dark:bg-red-900/40 dark:text-red-300"
              >
                Retry
              </button>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* ── Ready-to-generate summary card ──────────────────────────── */}
        {readyToGenerate && phase === 'chatting' && (
          <div className="shrink-0 border-t border-[var(--_border)] bg-[var(--_card)] px-4 py-3">
            <p className="mb-2 text-xs font-semibold text-[var(--_muted-fg)]">Trip summary</p>
            {summary && <p className="mb-3 text-sm font-medium text-[var(--_fg)]">{summary}</p>}
            <button
              type="button"
              onClick={handleGenerate}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--_primary)] py-3 text-sm font-bold text-white shadow transition-opacity hover:opacity-90"
            >
              <Plane size={15} />
              Generate my itinerary
            </button>
          </div>
        )}

        {/* ── Input bar ───────────────────────────────────────────────── */}
        {phase === 'chatting' && !readyToGenerate && (
          <div className="shrink-0 border-t border-[var(--_border)] bg-[var(--_card)] px-3 py-3">
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
                placeholder={voiceActive ? 'Listening…' : 'Type your reply…'}
                disabled={isSending || voiceActive}
                className="flex-1 rounded-xl border border-[var(--_border)] bg-[var(--_bg)] px-3 py-2.5 text-sm text-[var(--_fg)] placeholder:text-[var(--_muted-fg)] focus:border-[var(--_primary)] focus:outline-none disabled:opacity-50"
                aria-label="Message to Anya"
              />
              <button
                type="button"
                onClick={toggleVoice}
                aria-label={voiceActive ? 'Stop voice' : 'Voice input'}
                className={[
                  'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border transition-colors',
                  voiceActive
                    ? 'border-red-400 bg-red-50 text-red-500 dark:border-red-600 dark:bg-red-950/40 dark:text-red-400'
                    : 'border-[var(--_border)] text-[var(--_muted-fg)] hover:border-[var(--_primary)] hover:text-[var(--_primary)]',
                ].join(' ')}
              >
                {voiceActive ? <MicOff size={16} /> : <Mic size={16} />}
              </button>
              <button
                type="button"
                onClick={() => handleSubmit()}
                disabled={!input.trim() || isSending}
                aria-label="Send message"
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--_primary)] text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Send size={15} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
