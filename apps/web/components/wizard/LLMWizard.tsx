'use client'

import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useRouter } from 'next/navigation'
import { Mic, MicOff, Send, Plane, X, CheckCircle2, Loader2, Volume2 } from 'lucide-react'
import { useAppStore } from '@/store/appStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useWizardChatStore } from '@/store/wizardChatStore'
import { useAuthStore } from '@/store/authStore'
import { useFeedbackPromptStore } from '@/store/feedbackPromptStore'
import { wizardChat } from '@/lib/api'
import { streamItinerary, checkFeasibility, createAgentLead } from '@/lib/api'
import { formatFeasibilityBreakdown, suggestedFeasibleBudget, formatFeasibilityBreakdownDetailed } from '@/lib/feasibilityFormat'
import { savePendingGeneration, getPendingGeneration, clearPendingGeneration } from '@/lib/pendingGeneration'
import { formatCurrency } from '@/lib/format'
import { MAX_CHAT_MESSAGE_LEN } from '@/lib/limits'
import { VOICE_LANGS, type VoiceLang } from '@/lib/voice'
import { useVoice } from '@/hooks/useVoice'
import type { TripConfig, FeasibilityResponse } from '@/types'
import { WanderplannerLogo } from '@/components/common/WanderplannerLogo'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  chips?: string[]
  config_patch?: Record<string, unknown>  // stored so backend can replay real patches in history
  multiSelect?: boolean  // true when chips is a multi-value field (e.g. themes); server-computed
}

type Phase = 'chatting' | 'generating' | 'done'

interface ItineraryProgress {
  message: string
  step: number
  total: number
}

// A plain incrementing counter here would collide across Next.js Fast
// Refresh module re-evaluations in dev (the counter resets to 0 while the
// component's already-rendered message list — which survives Fast Refresh —
// keeps its old ids), producing duplicate React keys like "llm-msg-2" and
// the "two children with the same key" warnings/render glitches that come
// with it. crypto.randomUUID() (broadly supported) sidesteps this since it
// never depends on any module-level state.
const nextId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `llm-msg-${crypto.randomUUID()}`
  }
  // Fallback for environments without crypto.randomUUID (very old browsers).
  return `llm-msg-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

// Voice I/O lives in `lib/voice.ts` (pure helpers) and `hooks/useVoice.ts`
// (state and Web Speech API wiring). It used to be inline here, untested, with
// a single `voiceActive` flag standing in for both "the user wants a spoken
// conversation" and "the mic is open" — see the hook's docstring for what that
// conflation broke.

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

// Generic catch-all chips (e.g. "No preference") that can legitimately sit
// alongside a theme-chip group without being a theme themselves. They must
// be excluded before the "every chip looks like a theme" check below, or the
// whole group silently falls back to single-select — this was the actual
// bug, since the themes prompt always appends one of these.
const GENERIC_CHIP_KEYWORDS = ['no preference', 'none', 'skip', 'any', 'no thanks', 'not sure']

function _isThemeChipGroup(chips: string[]): boolean {
  if (chips.length < 2) return false
  const themeChips = chips.filter((c) => !GENERIC_CHIP_KEYWORDS.some((g) => c.toLowerCase().includes(g)))
  if (themeChips.length === 0) return false
  return themeChips.every((c) => THEME_CHIP_KEYWORDS.some((k) => c.toLowerCase().includes(k)))
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
      // Bug fix: this previously also counted flexible+duration_days alone
      // (with start/end still null) as "filled" — exactly the shape the
      // inspiration-card preload seeds before the user has said WHEN they
      // want to travel. That showed the Dates pill as complete (and could
      // even look ready to generate) while the backend's own gate
      // (_has_all_required in wizard_chat_chain.py) correctly still
      // requires a real start/end, and the exact travel period was never
      // actually asked for. A real start+end (even approximate month
      // boundaries for flexible trips) must be present to count as filled.
      return Boolean(d.start && d.end)
    }
    case 'budget':      return (config.budget?.amount ?? 0) > 0
    case 'group':       return (config.group?.adults ?? 0) >= 1
    case 'pace':        return Boolean(config.pace)
    default:            return false
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

export function LLMWizard() {
  const router            = useRouter()
  const closeWizard       = useAppStore((s) => s.closeWizard)
  const wizardPreload     = useAppStore((s) => s.wizardPreload)
  const clearPreload      = useAppStore((s) => s.clearWizardPreload)
  const setDays           = useItineraryStore((s) => s.setDays)
  const updateConfig      = useTripConfigStore((s) => s.updateConfig)
  const resetConfig       = useTripConfigStore((s) => s.resetConfig)
  const wizardReset       = useWizardChatStore((s) => s.reset)
  const authStatus        = useAuthStore((s) => s.status)

  const [messages, setMessages]       = useState<Message[]>([])
  const [input, setInput]             = useState('')
  const [phase, setPhase]             = useState<Phase>('chatting')
  const [isSending, setIsSending]     = useState(false)
  const [partialConfig, setPartialConfig] = useState<Partial<TripConfig>>({})
  const [summary, setSummary]         = useState<string | null>(null)
  const [progress, setProgress]       = useState<ItineraryProgress>({ message: '', step: 0, total: 6 })
  const [error, setError]             = useState('')
  // Voice notices are kept out of `error` on purpose: that banner carries a
  // Retry button wired to resend the last message, which makes no sense as a
  // response to "microphone access is blocked".
  const [voiceNotice, setVoiceNotice] = useState('')
  // Whether the one-time "choose a voice language" prompt is showing. Voice
  // language used to be a persistent toggle in the header — always taking up
  // space even for users who never touch voice — and on narrow screens it
  // crowded out the mic button entirely. Asking once, only when the user
  // actually starts a spoken conversation, means the header never has to
  // make room for it.
  const [voiceLangPrompt, setVoiceLangPrompt] = useState(false)
  // Whether we've already asked for a language this session. Session-scoped
  // (a ref, not persisted) rather than per-turn: the wizard component itself
  // is recreated each time it's opened, which is the granularity "once per
  // session" means here.
  const voiceLangAskedRef = useRef(false)
  // Per-message selection set, only used for multi-select theme chip groups
  const [themeSelections, setThemeSelections] = useState<Record<string, Set<string>>>({})
  // Gates the "Generate my itinerary" button, which used to call
  // handleGenerate() directly and so bypassed the feasibility check
  // entirely — a user could click it the instant the trip-summary card
  // appeared, before the automatic check even returned, or after it came
  // back infeasible/errored and the chips were showing. 'checking' is the
  // default (matches the card appearing exactly when the automatic check
  // starts); only 'feasible' enables the button.
  const [feasibilityState, setFeasibilityState] = useState<'checking' | 'feasible' | 'blocked' | 'idle'>('checking')
  // True while we're waiting on the user to type an email so the human
  // handoff (agent lead) can go out — only needed when they aren't signed
  // in, since a signed-in email is already known. See handleRequestHumanHelp.
  const [awaitingHandoffEmail, setAwaitingHandoffEmail] = useState(false)
  const [handoffSending, setHandoffSending] = useState(false)
  // Header copy only. This wizard and the orb chat are both "Anya", both
  // change the trip, and until now both introduced themselves with the same
  // words — so nothing told the user which surface they were in or what it
  // was for. The header is where that gets said, and reopening from "Edit
  // Trip" is a different job from first-run setup. Mirrors the bootstrap
  // effect's `isEditMode`; held as state because that condition reads the
  // stores as they were at bootstrap, not at render.
  const [isEditingTrip, setIsEditingTrip] = useState(false)

  // Always-current ref so sendMessage never reads stale partialConfig
  const partialConfigRef = useRef<Partial<TripConfig>>({})
  partialConfigRef.current = partialConfig

  // Snapshot any pending post-auth generation exactly once at mount (lazy
  // useState initializer), rather than each effect independently re-reading
  // sessionStorage. Both the resume-after-auth effect and the bootstrap
  // effect below need to agree on whether a resume is in flight — reading
  // fresh each time creates a race where the resume effect's own
  // `clearPendingGeneration()` call makes the bootstrap effect's guard see
  // "nothing pending" a moment later (since effects run in declaration
  // order within the same commit), causing it to also fire and inject a
  // brand-new "Hello, I'm Anya" greeting on top of the resumed generation.
  const [pendingGeneration] = useState<TripConfig | null>(() => getPendingGeneration())
  const hasResumedGenerationRef = useRef(false)

  const messagesEndRef  = useRef<HTMLDivElement>(null)
  const inputRef        = useRef<HTMLInputElement>(null)
  const cancelStreamRef = useRef<(() => void) | null>(null)
  // The exact config the last feasibility check was run against, so "Retry
  // check" re-verifies the same trip instead of re-reading whatever the
  // store happens to hold by the time the user clicks it.
  const lastFeasibilityConfigRef = useRef<TripConfig | null>(null)
  // The last infeasible result, so "Show budget breakdown" can render the
  // per-category detail without an extra round-trip to the API.
  const lastFeasibilityResultRef = useRef<FeasibilityResponse | null>(null)
  // Focus management for the modal dialog: `dialogRef` scopes the Tab trap
  // to content actually inside the card, and `previouslyFocusedRef` is
  // whatever had focus the instant this component mounted — i.e. whichever
  // of the wizard's several trigger buttons (header, hero CTA, inspiration
  // cards, floating orb) the user just activated — so focus can return
  // there when the wizard closes.
  const dialogRef = useRef<HTMLDivElement>(null)
  const previouslyFocusedRef = useRef<HTMLElement | null>(null)
  // Read by the voice hook's re-arm gate, which fires from a speech event and
  // so would otherwise capture whichever phase was current when voice mode
  // started.
  const phaseRef        = useRef<Phase>('chatting')
  phaseRef.current = phase
  // Watchdog for the generate-itinerary SSE stream: guards against the UI
  // getting stuck on "generating" forever if the stream silently dies with
  // no error event — e.g. a dropped connection, or (in dev) a Fast Refresh
  // remount aborting the underlying fetch, which the stream helper treats
  // as an intentional cancel and never reports as an error. Reset on every
  // status/data/error event; if it ever fires, that means total silence.
  const generationWatchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Fires once, at the soft threshold, to swap the loader copy to a "hang
  // tight" reassurance without touching the stream — see armGenerationWatchdog.
  const generationSoftWatchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // True while `error` holds a generate-itinerary failure (vs. a chat-turn
  // failure) — lets the shared error banner's Retry button re-run
  // generation instead of blindly resending the last chat message, which
  // previously left generation failures with no working retry path.
  const generationErrorRef = useRef(false)
  // Synchronous lock for in-flight sends. `isSending` (React state) only
  // takes effect on the NEXT render, so two click events dispatched in the
  // same tick (e.g. a duplicate click/touch event some browsers/devices
  // fire for a single tap, or a fast double-click on a chip) both read
  // `isSending` as false and both call sendMessage — the exact "every
  // question comes twice" symptom observed: the same chip answer submitted
  // twice, each getting its own real LLM round trip and reply. This ref is
  // set the instant a send starts, closing that window immediately.
  const sendingLockRef = useRef(false)

  // ── Voice I/O ──────────────────────────────────────────────────────────────

  // `handleSubmit` is a hoisted function declaration further down, so it is in
  // scope here; the hook only ever calls it from an event, never during render.
  const voice = useVoice({
    onTranscript: (text) => {
      setInput(text)
      handleSubmit(text)
    },
    onNotice: setVoiceNotice,
    // Don't reopen the mic once we've left the chat — during generation there
    // is nothing for the user to answer.
    canListen: () => phaseRef.current === 'chatting',
  })

  // ── Bootstrap first Anya message ───────────────────────────────────────────

  // Resume a generation that was interrupted by the sign-in gate — once the
  // user authenticates (including via the full-page-reload Google SSO
  // round-trip), pick the saved config back up and generate immediately
  // instead of re-running the whole chat conversation.
  useEffect(() => {
    if (authStatus !== 'authenticated') return
    if (!pendingGeneration || hasResumedGenerationRef.current) return
    hasResumedGenerationRef.current = true
    clearPendingGeneration()
    updateConfig(pendingGeneration)
    // Bug fix: this only used to update the Zustand trip-config store, never
    // the component's own local `partialConfig`/`messages` state that the
    // pill checklist and the post-error "chatting" view render from. Result:
    // right after sign-in, the wizard looked completely reset (every pill
    // gray, no chat history) while generation was silently in flight — and
    // if generation then failed for any reason (auth hiccup, timeout), the
    // user was dropped back into an empty-looking chat with no memory of
    // anything they'd already answered. Sync both so the wizard reflects
    // the resumed config immediately, and gracefully falls back to it.
    setPartialConfig(pendingGeneration)
    addMessage({
      role: 'assistant',
      content: "Welcome back! Picking up right where you left off — generating your itinerary now.",
    })
    // Bug fix: calling startGeneration() synchronously here is vulnerable to
    // React 18 Strict Mode's dev-only mount→cleanup→mount double-invoke —
    // the sibling "cleanup on unmount" effect below (empty deps) runs its
    // cleanup during React's synchronous phantom-unmount simulation, which
    // calls `cancelStreamRef.current?.()` and immediately aborts the fetch
    // this same tick just dispatched. Aborted fetches are treated as a
    // silent, deliberate cancel (no error surfaced, matching normal
    // navigate-away behaviour) — so the wizard was left frozen on "Starting
    // up..." forever with no error and no data ever arriving. Deferring the
    // actual kickoff to a macrotask lets it run *after* the synchronous
    // double-invoke settles (cancelStreamRef.current is still null when the
    // phantom cleanup fires, making it a harmless no-op), while a genuine
    // unmount shortly after would still correctly abort it.
    const timer = setTimeout(() => startGeneration(pendingGeneration), 0)
    // Deliberately no cleanup here: returning one would itself be cleared by
    // this same effect's own Strict Mode phantom-cleanup pass, permanently
    // cancelling the only scheduled kickoff before it ever runs (the ref
    // guard above already prevents the effect from re-scheduling on the
    // subsequent phantom re-mount). A genuine unmount shortly after is still
    // safely handled — the sibling cleanup-on-unmount effect aborts
    // `cancelStreamRef.current` once it's actually set.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authStatus, pendingGeneration])

  useEffect(() => {
    // If a generation is pending resume (see effect above), skip the normal
    // chat bootstrap entirely — it'll either auto-generate momentarily, or
    // the user is still off completing sign-in. Uses the same mount-time
    // snapshot as the resume effect above (not a fresh sessionStorage read)
    // so the two effects can never disagree about whether a resume is in
    // flight, regardless of effect execution order.
    if (pendingGeneration) return

    const preload = wizardPreload
    const preloadLabel = preload ? `${preload.city}, ${preload.country}` : undefined

    // ── Edit mode: reopening the wizard from "Edit Trip" on an already-
    // generated itinerary should carry the existing config forward instead
    // of starting a brand-new conversation from scratch.
    const existingConfig = useTripConfigStore.getState().config
    const hasExistingItinerary = useItineraryStore.getState().days.length > 0
    const isEditMode = !preload && hasExistingItinerary
      && REQUIRED_LABELS.every(({ key }) => _isFieldFilled(key, existingConfig))

    if (isEditMode) {
      setIsEditingTrip(true)
      setPartialConfig({ ...existingConfig, _checkpoint_asked: true } as Partial<TripConfig>)

      const destLabel = existingConfig.destination_mode === 'country'
        ? (existingConfig.destination_country ?? 'your destination')
        : existingConfig.hops.length > 0
          ? `${existingConfig.destination?.city} +${existingConfig.hops.length} more`
          : (existingConfig.destination?.city ?? 'your destination')
      const durationLabel = existingConfig.dates.duration_days
        ? `${existingConfig.dates.duration_days} days`
        : existingConfig.dates.start && existingConfig.dates.end
          ? `${existingConfig.dates.start} – ${existingConfig.dates.end}`
          : ''
      const summaryLine = [
        destLabel,
        durationLabel,
        formatCurrency(existingConfig.budget.amount, existingConfig.budget.currency),
        `${existingConfig.group.adults} adult${existingConfig.group.adults !== 1 ? 's' : ''}`,
        existingConfig.pace,
      ].filter(Boolean).join(' · ')

      addMessage({
        role: 'assistant',
        content: `Welcome back! Here's your current trip: ${summaryLine}. What would you like to change — destination, dates, budget, or themes? Or tell me to regenerate it as-is.`,
        chips: ['Change destination', 'Change dates', 'Change budget', 'Add/change themes', 'Regenerate as-is'],
      })
      setPhase('chatting')
      return
    }

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

  // useVoice cleans up its own recognition and synthesis on unmount.
  useEffect(() => {
    return () => {
      cancelStreamRef.current?.()
      clearGenerationWatchdog()
    }
  }, [])

  // ── Modal focus management ──────────────────────────────────────────────────

  // Move focus into the dialog on open, and back to whatever triggered it on
  // close. Without this, the mic/toolbar buttons this component uses as its
  // "first focusable element" would otherwise be reached only by tabbing in
  // from wherever the page happened to leave focus — or, on close, focus
  // would fall back to <body>, silently dropping keyboard users at the top
  // of the page.
  useEffect(() => {
    previouslyFocusedRef.current = document.activeElement as HTMLElement | null
    const toFocus = dialogRef.current?.querySelector<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
    toFocus?.focus()

    return () => {
      previouslyFocusedRef.current?.focus?.()
    }
  }, [])

  /** Escape closes the wizard; Tab/Shift+Tab is trapped within the dialog card. */
  function handleDialogKeyDown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.stopPropagation()
      cancelStreamRef.current?.()
      closeWizard()
      return
    }
    if (e.key !== 'Tab' || !dialogRef.current) return

    const focusable = Array.from(
      dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
      )
    ).filter((el) => el.offsetParent !== null) // skip hidden elements
    if (focusable.length === 0) return

    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    const active = document.activeElement

    if (e.shiftKey && active === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && active === last) {
      e.preventDefault()
      first.focus()
    }
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  function addMessage(msg: Omit<Message, 'id'>) {
    setMessages((prev) => [...prev, { ...msg, id: nextId() }])
  }

  // ── Send a message to Anya ─────────────────────────────────────────────────

  async function sendMessage(
    text: string,
    currentMessages: Message[] = messages,
    preloadLabel?: string,
  ) {
    // Synchronous re-entrancy guard — see sendingLockRef declaration for why
    // the `isSending` state check alone isn't enough to stop a duplicate
    // send from the same tick.
    if (sendingLockRef.current) return
    sendingLockRef.current = true

    const isBootstrap = text === '__START__'
    const displayText = isBootstrap ? '' : text

    const nextMessages: Message[] = isBootstrap
      ? currentMessages
      : [...currentMessages, { id: nextId(), role: 'user', content: displayText }]

    if (!isBootstrap) setMessages(nextMessages)
    setIsSending(true)
    setError('')
    generationErrorRef.current = false

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

      // Merge config_patch into partialConfig (computed once so we can reuse
      // the merged shape for the feasibility gate below, since React state
      // updates aren't synchronously readable via partialConfigRef here).
      const mergedPartial: Partial<TripConfig> = { ...partialConfigRef.current }
      if (res.config_patch && Object.keys(res.config_patch).length > 0) {
        for (const [k, v] of Object.entries(res.config_patch)) {
          if (typeof v === 'object' && v !== null && !Array.isArray(v) && typeof mergedPartial[k as keyof TripConfig] === 'object') {
            mergedPartial[k as keyof TripConfig] = { ...(mergedPartial[k as keyof TripConfig] as object), ...v } as never
          } else {
            mergedPartial[k as keyof TripConfig] = v as never
          }
        }
      }
      // Coerce group.kids from plain integers to KidAge objects (LLM may emit [3, 6])
      const gCoerce = mergedPartial.group as Record<string, unknown> | undefined
      if (gCoerce && Array.isArray(gCoerce.kids)) {
        gCoerce.kids = (gCoerce.kids as unknown[]).map((k) =>
          typeof k === 'number' ? { age: k } : k
        )
      }
      // Track that the "anything else?" checkpoint has been shown
      // once all 6 fields are filled, so the LLM doesn't re-ask next turn
      const allFilledCheck = REQUIRED_LABELS.every(({ key }) => _isFieldFilled(key, mergedPartial))
      if (allFilledCheck && !(mergedPartial as Record<string, unknown>)._checkpoint_asked) {
        (mergedPartial as Record<string, unknown>)._checkpoint_asked = true
      }
      setPartialConfig(mergedPartial)

      const assistantMsg: Message = {
        id: nextId(),
        role: 'assistant',
        content: res.reply,
        chips: res.chips.length > 0 ? res.chips : undefined,
        config_patch: Object.keys(res.config_patch ?? {}).length > 0 ? res.config_patch : undefined,
        multiSelect: res.multi_select,
      }
      setMessages([...nextMessages, assistantMsg])

      // No-op unless voice mode is on. The check lives inside the hook, read
      // from a ref — doing it here is what made this line dead code before.
      voice.speakReply(res.reply, res.reply_sig)

      if (res.ready_to_generate) {
        setSummary(res.summary)
        // Budget feasibility gate (⭐ NEW): before auto-generating, verify the
        // collected budget can actually cover the trip (real deterministic
        // floor + LLM cost estimate — see chains/feasibility_chain.py). If
        // it's short, pause and let the user increase the budget, change
        // destination, or explicitly proceed anyway rather than silently
        // generating an itinerary the stated budget can't realistically cover.
        const configForCheck = { ...useTripConfigStore.getState().config, ...mergedPartial } as TripConfig
        runFeasibilityGate(configForCheck)
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
      sendingLockRef.current = false
    }
  }

  // ── Budget feasibility gate ─────────────────────────────────────────────────
  // No "proceed anyway" bypass here on purpose — a gate that can be
  // overridden with one click isn't a gate. The only ways forward on an
  // infeasible budget are raising it (the suggested-budget chip), viewing
  // the breakdown to decide what to cut, changing the trip (freeform
  // "adjust something else"), or asking a human — the deck's "can't safely
  // price it → hands to a human" claim needs a real path here, not just on
  // the (unreachable, since we now block generation) itinerary page's
  // "Get Quotation" card.
  const RETRY_CHECK_CHIP = 'Retry check 🔁'
  const START_OVER_CHIP = 'Start over 🔄'
  const SHOW_BREAKDOWN_CHIP = 'Show budget breakdown 📊'
  const HUMAN_HELP_CHIP = 'Talk to a human instead 🧑‍💼'
  // Deliberately distinct from the budget gate's (banned) "proceed anyway":
  // a nonexistent-destination check has a much higher false-negative rate
  // (real places routinely miss our geocoder) than a budget shortfall does,
  // so overriding it is reasonable here in a way it never is for money.
  const CONTINUE_ANYWAY_CHIP = "It's a real place, continue anyway ➡️"
  const FIX_DESTINATION_CHIP = 'Let me fix the destination'

  /** Best-effort trip summary for the human-handoff lead, built straight
   * from the in-progress wizard config — there is no itinerary yet (that's
   * the whole reason this option exists), so unlike AgentHandoffCard on the
   * itinerary page, itinerary_html/pdf_base64 are simply omitted (both are
   * optional on the backend). */
  function buildHandoffTripSummary() {
    const cfg = partialConfigRef.current
    return {
      destination: cfg.destination?.city || cfg.destination_country || '',
      dates: cfg.dates,
      budget: cfg.budget,
      group: cfg.group,
      purpose: cfg.purpose,
      pace: cfg.pace,
    }
  }

  async function submitHumanHandoff(email: string) {
    const summary = buildHandoffTripSummary()
    setAwaitingHandoffEmail(false)
    if (!summary.destination) {
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: 'assistant', content: "I don't have a destination to send yet — let's finish that first." },
      ])
      return
    }
    setHandoffSending(true)
    try {
      const result = await createAgentLead({
        email,
        destination: summary.destination,
        source: 'infeasible_budget',
        trip_config_summary: summary,
        custom_notes: 'Requested from the trip-planning chat — the stated budget did not cover the trip and the traveller asked for a human instead of raising it.',
      })
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: 'assistant',
          content: result.duplicate
            ? "You've already sent this request today — a destination specialist will still reply to you within 24 hours, no need to resend."
            : '✅ Request sent — a destination specialist will reply to you within 24 hours.',
        },
      ])
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: 'assistant', content: "⚠️ Couldn't send that request just now — please try again in a moment.", chips: [HUMAN_HELP_CHIP] },
      ])
    } finally {
      setHandoffSending(false)
    }
  }

  /** Entry point for the "Talk to a human instead" chip — uses the
   * signed-in user's email if we already have one, otherwise asks for it
   * as a plain chat reply (captured by the awaitingHandoffEmail branch in
   * handleSubmit) before submitting the lead. */
  function handleRequestHumanHelp() {
    const knownEmail = useAuthStore.getState().user?.email
    if (knownEmail) {
      submitHumanHandoff(knownEmail)
      return
    }
    setAwaitingHandoffEmail(true)
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: 'assistant', content: "What's the best email for the specialist to reach you at?" },
    ])
  }

  /** Wipes chat + config back to a blank wizard — the "discard and start
   * fresh" option offered when we can't verify feasibility and won't let
   * the user proceed blind. Distinct from `closeWizard()`: this keeps the
   * wizard open, ready for a brand-new trip, rather than dismissing it. */
  function handleStartOver() {
    wizardReset()
    resetConfig()
    setMessages([])
    setPartialConfig({})
    setSummary(null)
    setThemeSelections({})
    setError('')
    setFeasibilityState('checking')
    setAwaitingHandoffEmail(false)
    lastFeasibilityConfigRef.current = null
    lastFeasibilityResultRef.current = null
  }

  async function runFeasibilityGate(fullConfig: TripConfig, skipDestinationCheck = false) {
    lastFeasibilityConfigRef.current = fullConfig
    setFeasibilityState('checking')
    try {
      const result = await checkFeasibility(fullConfig, skipDestinationCheck)
      if (result.destination_verified === false) {
        // Distinct, earlier check than budget feasibility — a nonexistent
        // destination has no meaningful cost to estimate. NOT a hard block
        // (unlike budget infeasibility): real places are routinely missing
        // from our geocoder, so offer both "fix it" and "continue anyway".
        setFeasibilityState('blocked')
        lastFeasibilityResultRef.current = result
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: 'assistant',
            content: result.verdict,
            chips: [CONTINUE_ANYWAY_CHIP, FIX_DESTINATION_CHIP, HUMAN_HELP_CHIP],
          },
        ])
        return
      }
      if (result.feasible) {
        setFeasibilityState('feasible')
        setTimeout(() => handleGenerate(), 1200)
        return
      }
      // Infeasible — surface the real shortfall + a real suggested minimum
      // (never silently generate against a budget that can't cover the trip).
      // IMPORTANT: always suggest the SAME total the verdict/shortfall was
      // computed against — see suggestedFeasibleBudget's docstring.
      setFeasibilityState('blocked')
      lastFeasibilityResultRef.current = result
      const minBudget = suggestedFeasibleBudget(result)
      const breakdownText = formatFeasibilityBreakdown(result)
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: 'assistant',
          content: `${result.verdict} Breakdown: ${breakdownText}. This is a bare-minimum estimate (activities/shopping extra). Increase your budget to around ₹${minBudget.toLocaleString('en-IN')}, see the full breakdown to decide what to cut, tell me what to change, or talk to a human instead.`,
          chips: [`Set budget to ₹${minBudget.toLocaleString('en-IN')}`, SHOW_BREAKDOWN_CHIP, HUMAN_HELP_CHIP, 'Let me adjust something else'],
        },
      ])
    } catch {
      // Feasibility check itself failed (network/server) — this used to
      // silently fall back to generating anyway, which meant a budget that
      // could genuinely be short (or wildly short, per the live example
      // that surfaced this) landed on an itinerary page with no warning
      // until "Edit Trip" — after the fact. We cannot claim a budget is
      // fine when we couldn't check it, so stop here instead: no
      // itinerary until the user explicitly says how to proceed.
      setFeasibilityState('blocked')
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: 'assistant',
          content: "I couldn't verify whether this budget realistically covers the trip just now (a connection hiccup on my end) — I won't generate an itinerary without checking that first. Want to retry the check, adjust something (budget, dates, destination) yourself, talk to a human, or start over completely?",
          chips: [RETRY_CHECK_CHIP, HUMAN_HELP_CHIP, START_OVER_CHIP],
        },
      ])
    }
  }

  // ── User submits a message ─────────────────────────────────────────────────

  async function handleSubmit(text?: string) {
    const value = (text ?? input).trim()
    if (!value || isSending || sendingLockRef.current || phase !== 'chatting') return
    if (value === HUMAN_HELP_CHIP) {
      setMessages((prev) => [...prev, { id: nextId(), role: 'user', content: value }])
      setInput('')
      handleRequestHumanHelp()
      return
    }
    if (awaitingHandoffEmail) {
      // The previous turn asked for an email to send the human-handoff
      // lead to — treat this reply as that email rather than routing it
      // through the normal wizard chat turn.
      setMessages((prev) => [...prev, { id: nextId(), role: 'user', content: value }])
      setInput('')
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
        setMessages((prev) => [
          ...prev,
          { id: nextId(), role: 'assistant', content: "That doesn't look like a valid email — could you try again?" },
        ])
        return
      }
      await submitHumanHandoff(value)
      return
    }
    if (value === SHOW_BREAKDOWN_CHIP) {
      // Render the per-category detail from the already-fetched result —
      // no extra API round-trip — so the user has something concrete to
      // point at ("cut accommodation") instead of just a total shortfall.
      setMessages((prev) => [...prev, { id: nextId(), role: 'user', content: value }])
      const lastResult = lastFeasibilityResultRef.current
      if (lastResult) {
        const minBudget = suggestedFeasibleBudget(lastResult)
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: 'assistant',
            content: formatFeasibilityBreakdownDetailed(lastResult),
            chips: [`Set budget to ₹${minBudget.toLocaleString('en-IN')}`, 'Let me adjust something else'],
          },
        ])
      }
      return
    }
    if (value === RETRY_CHECK_CHIP) {
      // Re-verify the same trip the failed check was run against, rather
      // than silently generating — see runFeasibilityGate's catch block.
      setMessages((prev) => [...prev, { id: nextId(), role: 'user', content: value }])
      const retryConfig = lastFeasibilityConfigRef.current
      if (retryConfig) {
        await runFeasibilityGate(retryConfig)
      }
      return
    }
    if (value === START_OVER_CHIP) {
      // No point echoing the user's chip choice first — handleStartOver
      // wipes the whole message list immediately after anyway.
      handleStartOver()
      return
    }
    if (value === CONTINUE_ANYWAY_CHIP) {
      // User asserts the destination IS real despite our geocoder missing
      // it — high false-negative-rate check (see runFeasibilityGate), so
      // this is a legitimate override, unlike the budget gate's "Proceed
      // anyway" which was removed entirely. Re-run the SAME config with
      // skip_destination_check so the rest of the gate (budget) still runs.
      setMessages((prev) => [...prev, { id: nextId(), role: 'user', content: value }])
      const retryConfig = lastFeasibilityConfigRef.current
      if (retryConfig) {
        await runFeasibilityGate(retryConfig, true)
      }
      return
    }
    if (value === FIX_DESTINATION_CHIP) {
      // Clear the unverified destination so the wizard re-asks for it on
      // the next turn, instead of leaving the stale (unverified) value in
      // partialConfig where a later "Generate" could silently reuse it.
      setMessages((prev) => [...prev, { id: nextId(), role: 'user', content: value }])
      lastFeasibilityConfigRef.current = null
      lastFeasibilityResultRef.current = null
      setFeasibilityState('idle')
      const { destination: _dest, ...rest } = partialConfigRef.current
      setPartialConfig(rest)
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: 'assistant',
          content: 'No problem — where would you like to go instead?',
        },
      ])
      return
    }
    setInput('')
    await sendMessage(value)
  }

  // ── Generate itinerary ─────────────────────────────────────────────────────

  function clearGenerationWatchdog() {
    if (generationWatchdogRef.current !== null) {
      clearTimeout(generationWatchdogRef.current)
      generationWatchdogRef.current = null
    }
    if (generationSoftWatchdogRef.current !== null) {
      clearTimeout(generationSoftWatchdogRef.current)
      generationSoftWatchdogRef.current = null
    }
  }

  // (Re)arms the stuck-generation watchdogs. Called on start and after every
  // status update, so they only ever fire on total silence, never mid-progress.
  //
  // Two stages, not one: a cold-cache destination's live Wikivoyage/OSM/
  // YouTube scrape (plus embedding work that can briefly block the event
  // loop — see docs/scaling-tech-challenges.md's single-process note) can
  // legitimately run close to the backend's own 120s LLM_TIMEOUT_SECONDS
  // ceiling, and it usually *does* still land a 200 — retrying a request
  // that's actually about to succeed just makes the user wait through the
  // same slow path twice. The old single 60s timeout cancelled the stream
  // and forced a retry well before that ceiling, on a request that was
  // still working. Soft stage now just reassures the user in place while
  // the stream keeps listening; only the hard stage (past the backend's own
  // ceiling, with margin) gives up and offers Retry.
  function armGenerationWatchdog() {
    clearGenerationWatchdog()
    generationSoftWatchdogRef.current = setTimeout(() => {
      setProgress((prev) => ({ ...prev, message: 'Still working — this destination is taking a bit longer than usual. Hang tight…' }))
    }, 60_000)
    generationWatchdogRef.current = setTimeout(() => {
      cancelStreamRef.current?.()
      generationErrorRef.current = true
      setError('Generation is taking much longer than expected and may have stalled. Please try again.')
      setPhase('chatting')
    }, 150_000) // margin past the backend's 120s LLM_TIMEOUT_SECONDS ceiling, so a
                // genuinely still-working request finishes (or the backend's own
                // LLM_TIMEOUT error event arrives) before this ever fires.
  }

  function startGeneration(fullConfig: TripConfig) {
    generationErrorRef.current = false
    setPhase('generating')
    setProgress({ message: 'Starting up…', step: 0, total: 6 })
    wizardReset()
    armGenerationWatchdog()

    cancelStreamRef.current = streamItinerary(
      fullConfig,
      (msg, step, total) => {
        armGenerationWatchdog()
        setProgress({ message: msg, step, total })
      },
      (result) => {
        clearGenerationWatchdog()
        setDays(result.days, result.alignment_score, result.expense_breakdown, result.generation_tier, result.warnings)
        setPhase('done')
        closeWizard()
        // The itinerary has its own route now, so finishing generation is a
        // navigation, not just a state change.
        router.push('/itinerary')
      },
      (code, message, _retryable) => {
        clearGenerationWatchdog()
        // Session expired mid-flow (or was never established) — save the
        // fully-collected config and send the user to sign in, then resume
        // generation automatically once they're back (see resume effect).
        if (code === 'AUTH_REQUIRED') {
          savePendingGeneration(fullConfig)
          router.push(`/signup?returnTo=${encodeURIComponent('/')}`)
          return
        }
        generationErrorRef.current = true
        setError(`Generation failed: ${message} (${code})`)
        setPhase('chatting')
      },
    )
  }

  function handleGenerate() {
    // Use ref to avoid stale closure (called from setTimeout or button click)
    updateConfig(partialConfigRef.current as Partial<TripConfig>)

    // Build a full TripConfig from the partialConfig + store defaults
    const fullConfig = useTripConfigStore.getState().config

    // Require sign-in before generating — matches the itinerary-gate
    // enforced server-side in /generate-itinerary.
    if (useAuthStore.getState().status !== 'authenticated') {
      savePendingGeneration(fullConfig)
      router.push(`/signup?returnTo=${encodeURIComponent('/')}`)
      return
    }

    // Regenerating replaces whatever itinerary is currently on screen —
    // if one exists, ask for a reaction on it before it's gone. A brand
    // new (first-ever) generation has nothing to react to yet.
    if (useItineraryStore.getState().days.length > 0) {
      useFeedbackPromptStore.getState().request('generate')
    }

    startGeneration(fullConfig)
  }

  // ── Voice controls ─────────────────────────────────────────────────────────

  function handleToggleVoice() {
    setVoiceNotice('')
    // First time starting a spoken conversation this session: ask which
    // language, once, instead of turning the mic on immediately. Every
    // subsequent toggle (on or off) reuses the answer.
    if (!voice.voiceMode && !voiceLangAskedRef.current) {
      setVoiceLangPrompt(true)
      return
    }
    voice.toggleVoiceMode()
  }

  function handleVoiceLangChange(next: VoiceLang) {
    setVoiceNotice('')
    voice.setLang(next)
  }

  /** User picked a language from the one-time prompt: apply it and start listening. */
  function handleChooseVoiceLang(next: VoiceLang) {
    voiceLangAskedRef.current = true
    setVoiceLangPrompt(false)
    handleVoiceLangChange(next)
    voice.toggleVoiceMode()
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
      onKeyDown={handleDialogKeyDown}
      className="fixed inset-0 z-50 flex items-end justify-center bg-white/30 backdrop-blur-md sm:items-center dark:bg-black/30"
    >
      <div ref={dialogRef} className="relative flex w-full max-h-screen flex-col overflow-hidden bg-[var(--_card)] sm:mx-4 sm:max-h-[90vh] sm:max-w-lg sm:rounded-2xl rounded-t-2xl shadow-2xl">

        {/* ── Header ──────────────────────────────────────────────────── */}
        <div className="flex shrink-0 items-center justify-between bg-[var(--_primary)] px-5 py-4 text-white">
          <div className="flex items-center gap-3">
            <WanderplannerLogo size="sm" inverted />
            <div>
              <p className="text-sm font-bold leading-tight">Anya</p>
              {/* Says the job, not the persona — "AI travel concierge" was
                  also the orb chat's subtitle, so the two surfaces were
                  indistinguishable once open. Here Anya asks and you answer;
                  in the chat you ask. */}
              <p className="text-xs text-white/70">
                {isEditingTrip ? 'Guided changes' : 'Guided setup'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Language is no longer a persistent header toggle — it used to
                compete with this mic button for space and get clipped on
                narrow screens. It's now asked once, only when the user
                starts a spoken conversation (see the language-prompt overlay
                below), then reused for the rest of the session. */}
            <button
              type="button"
              onClick={handleToggleVoice}
              aria-label={voice.voiceMode ? 'Stop voice mode' : 'Start voice mode'}
              aria-pressed={voice.voiceMode}
              disabled={!voice.supported}
              title={
                voice.supported
                  ? undefined
                  : 'Voice input isn’t supported in this browser'
              }
              className={[
                'flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors duration-300',
                !voice.supported
                  // Idle / unavailable: greyed out, not interactive-looking.
                  ? 'cursor-not-allowed bg-white/10 text-white/30'
                  : voice.isListening
                    // Active: the one state that should visually pop, with
                    // motion — the mic is genuinely capturing audio right now.
                    // Green reads as "live" (recording light, call-in-progress,
                    // online dot) without the alarm/failure connotation red
                    // carries elsewhere in this app (`--_destructive`).
                    ? 'bg-emerald-400 text-emerald-950 animate-pulse'
                    : voice.voiceMode
                      // Voice mode on, mic momentarily closed (e.g. Anya is
                      // replying): a quieter "on" state, no animation.
                      ? 'bg-white text-[var(--_primary)]'
                      // Not in use: greyed out, matching the unavailable state.
                      : 'bg-white/15 text-white/50 hover:bg-white/25 hover:text-white',
              ].join(' ')}
            >
              {voice.isSpeaking
                ? <Volume2 size={16} />
                : !voice.supported
                  ? <MicOff size={16} />
                  : <Mic size={16} />}
            </button>
            <button
              type="button"
              onClick={() => { cancelStreamRef.current?.(); closeWizard() }}
              aria-label="Close"
              className="flex h-11 w-11 items-center justify-center rounded-full bg-white/20 text-white hover:bg-white/30"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* ── One-time voice-language prompt ─────────────────────────────
            Shown once per session, the moment the user first starts a
            spoken conversation — replaces the old always-visible header
            toggle (see handleToggleVoice). */}
        {voiceLangPrompt && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/40 p-6">
            <div className="w-full max-w-xs rounded-2xl bg-[var(--_card)] p-5 text-center shadow-xl">
              <p className="mb-1 text-sm font-semibold text-[var(--_fg)]">
                Which language would you like to speak?
              </p>
              <p className="mb-4 text-xs text-[var(--_muted-fg)]">
                Anya will listen and reply in this language for the rest of the conversation.
              </p>
              <div className="flex justify-center gap-3">
                {(Object.keys(VOICE_LANGS) as VoiceLang[]).map((code) => (
                  <button
                    key={code}
                    type="button"
                    onClick={() => handleChooseVoiceLang(code)}
                    aria-label={`Speak and listen in ${VOICE_LANGS[code].label}`}
                    className="rounded-full border border-[var(--_border)] px-4 py-2 text-sm font-semibold text-[var(--_fg)] transition-colors hover:border-[var(--_primary)] hover:text-[var(--_primary)]"
                  >
                    {VOICE_LANGS[code].nativeLabel}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setVoiceLangPrompt(false)}
                className="mt-4 text-xs text-[var(--_muted-fg)] underline"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* ── Progress bar ────────────────────────────────────────────── */}
        <div
          role="progressbar"
          aria-valuenow={progressPct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Trip details ${progressPct}% complete`}
          className="relative h-1 w-full shrink-0 overflow-hidden bg-[var(--_primary)]/20"
        >
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
                      // Prefer the server-computed flag (reliable); fall back to the
                      // keyword heuristic only for older/cached messages that predate it.
                      const isThemeGroup = msg.multiSelect ?? _isThemeChipGroup(visibleChips)
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
                                  'rounded-full border border-[var(--_primary)] px-3.5 py-2 text-xs font-medium transition-colors disabled:opacity-50',
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
            <div
              role="progressbar"
              aria-valuenow={progress.total > 0 ? Math.round((progress.step / progress.total) * 100) : undefined}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={progress.message || 'Generating your itinerary'}
              className="flex items-center gap-3 rounded-2xl border border-[var(--_border)] bg-[var(--_card)] px-4 py-3"
            >
              <Loader2 size={16} className="shrink-0 animate-spin text-[var(--_primary)]" aria-hidden="true" />
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
            <div role="alert" className="flex items-center gap-2 rounded-xl bg-red-50 px-3 py-2 dark:bg-red-950/40">
              <p className="flex-1 text-xs text-red-600 dark:text-red-400">{error}</p>
              <button
                type="button"
                onClick={() => {
                  setError('')
                  // Generation failures (incl. the stall watchdog) need to
                  // re-run generation itself — resending the last chat
                  // message just re-confirmed "proceed?" and never actually
                  // retried, leaving the user stuck after a failed generate.
                  if (generationErrorRef.current) {
                    generationErrorRef.current = false
                    startGeneration(useTripConfigStore.getState().config)
                    return
                  }
                  const lastUser = [...messages].reverse().find((m) => m.role === 'user')
                  if (lastUser) {
                    setMessages((prev) => prev.slice(0, -1)) // remove last user msg to re-send
                    sendMessage(lastUser.content, messages.slice(0, -1))
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
            {/* Disabled until the automatic feasibility check comes back
                feasible — this button used to call handleGenerate()
                directly, bypassing the check entirely regardless of
                whether it was still running, had failed, or had come back
                infeasible (in which case the chips above are the intended
                way forward, not this button). */}
            <button
              type="button"
              onClick={handleGenerate}
              disabled={feasibilityState !== 'feasible'}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--_primary)] py-3 text-sm font-bold text-white shadow transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {feasibilityState === 'checking' ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  Checking your budget…
                </>
              ) : feasibilityState === 'blocked' ? (
                <>
                  <Plane size={15} />
                  Resolve the budget check above first
                </>
              ) : (
                <>
                  <Plane size={15} />
                  Generate my itinerary
                </>
              )}
            </button>
          </div>
        )}

        {/* ── Input bar ───────────────────────────────────────────────── */}
        {/* Always available while chatting — even once ready-to-generate,
            so the user can still ask a question or push back (e.g. on a
            feasibility warning) instead of only having quick-reply chips. */}
        {phase === 'chatting' && (
          <div className="shrink-0 border-t border-[var(--_border)] bg-[var(--_card)] px-3 py-3">
            {/* Voice status and failures. `role="status"` so a screen reader
                announces "microphone blocked" — the case that previously
                produced no feedback of any kind. */}
            {(voiceNotice || voice.isSpeaking || voice.isListening) && (
              <p
                role="status"
                aria-live="polite"
                className="mb-2 px-1 text-xs text-[var(--_muted-fg)]"
              >
                {voiceNotice
                  ? voiceNotice
                  : voice.isListening
                    ? `Listening in ${VOICE_LANGS[voice.lang].label}…`
                    : 'Anya is speaking…'}
              </p>
            )}
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
                placeholder={voice.isListening ? 'Listening…' : 'Type your reply…'}
                maxLength={MAX_CHAT_MESSAGE_LEN}
                // Only blocked while the mic is actually open. Disabling for
                // the whole voice-mode session meant switching to voice took
                // typing away entirely, with no way back but toggling off.
                disabled={isSending || voice.isListening || handoffSending}
                className="flex-1 rounded-xl border border-[var(--_border)] bg-[var(--_bg)] px-3 py-2.5 text-sm text-[var(--_fg)] placeholder:text-[var(--_muted-fg)] focus:border-[var(--_primary)] focus:outline-none disabled:opacity-50"
                aria-label="Message to Anya"
              />
              <button
                type="button"
                onClick={handleToggleVoice}
                aria-label={voice.voiceMode ? 'Stop voice' : 'Voice input'}
                aria-pressed={voice.voiceMode}
                disabled={!voice.supported}
                className={[
                  'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border transition-colors duration-300',
                  !voice.supported
                    // Idle / unavailable: greyed out, not interactive-looking.
                    ? 'cursor-not-allowed border-[var(--_border)] text-[var(--_muted-fg)] opacity-50'
                    : voice.isListening
                      // Active: the one state that should visually pop, with
                      // motion — the mic is genuinely capturing audio right now.
                      // Green ("live", like a recording light) rather than red
                      // avoids implying something has stopped or gone wrong —
                      // this app's red (`--_destructive`) means exactly that.
                      ? 'border-emerald-400 bg-emerald-50 text-emerald-600 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-400 animate-pulse'
                      : voice.voiceMode
                        // Voice mode on, mic momentarily closed (e.g. Anya is
                        // replying): a quieter "on" state, no animation.
                        ? 'border-[var(--_primary)] text-[var(--_primary)]'
                        // Not in use: greyed out, matching the unavailable state.
                        : 'border-[var(--_border)] text-[var(--_muted-fg)] hover:border-[var(--_primary)] hover:text-[var(--_primary)]',
                ].join(' ')}
              >
                {voice.isSpeaking
                  ? <Volume2 size={16} />
                  : !voice.supported
                    ? <MicOff size={16} />
                    : <Mic size={16} />}
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
