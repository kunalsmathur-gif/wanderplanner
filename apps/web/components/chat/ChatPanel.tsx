'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { X, Send, RefreshCw } from 'lucide-react'
import { useChatStore } from '@/store/chatStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useAppStore } from '@/store/appStore'
import { useAuthStore } from '@/store/authStore'
import { chatRefine, streamItinerary, checkFeasibility, sendGenerationSignal } from '@/lib/api'
import { savePendingGeneration } from '@/lib/pendingGeneration'
import { loadLastItinerary } from '@/lib/resumeLastItinerary'
import { diffItineraries, isEmptyDiff } from '@/lib/itineraryDiff'
import { formatFeasibilityBreakdown, suggestedFeasibleBudget, formatFeasibilityBreakdownDetailed } from '@/lib/feasibilityFormat'
import { MAX_CHAT_MESSAGE_LEN } from '@/lib/limits'
import { ChatMessage } from './ChatMessage'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import type { ChatRefineResponse, TripConfig, FeasibilityResponse } from '@/types'

const WELCOME =
  "Hi! I'm Anya ✈️\n\nAsk me anything about your trip, or tell me to change your destination, dates, budget, or preferences and I'll update your plan!"

// Natural-language "resume my last trip" intent (issue #65) — deliberately a
// simple keyword match rather than routing through chatRefine's LLM intent
// classifier: this only ever needs to catch "show/continue/resume ... last/
// previous trip/itinerary/plan", and a cheap client-side check means it
// never depends on (or waits on) a network round trip that could otherwise
// misclassify it as a regular refine request.
const RESUME_LAST_ITINERARY_INTENT = /\b(show|continue|resume|pull up|bring back|get)\b.{0,20}\b(my )?(last|previous|recent)\b.{0,20}\b(trip|itinerary|plan)\b/i

export function ChatPanel() {
  const router = useRouter()
  const { isOpen, close, messages, status, errorMsg, addMessage, setStatus } = useChatStore()
  const tripConfig = useTripConfigStore((s) => s.config)
  const updateConfig = useTripConfigStore((s) => s.updateConfig)

  const [input, setInput] = useState('')
  const [pendingAction, setPendingAction] = useState<ChatRefineResponse | null>(null)
  const [regenNote, setRegenNote] = useState<string | null>(null)
  // Mirrors LLMWizard's initial-generation feasibility gate for in-chat
  // regeneration (pin commits, "make day 3 cheaper", confirmed major
  // changes) — this path used to call streamItinerary directly with no
  // check at all, so a budget-busting edit landed on the itinerary page
  // with no warning until "Edit Trip", same bug class as the initial
  // generation path had before its gate was added.
  const [pendingFeasibility, setPendingFeasibility] = useState<{
    config: TripConfig
    kind: 'infeasible' | 'error' | 'destination_unverified'
    result?: FeasibilityResponse
    suggestedBudget?: number
  } | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const cancelRegenRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, regenNote])

  useEffect(() => {
    if (isOpen) setTimeout(() => inputRef.current?.focus(), 150)
  }, [isOpen])

  useEffect(() => () => cancelRegenRef.current?.(), [])

  /** Actually stream the regenerated itinerary — split out from
   * `regenerateInPlace` so the feasibility gate below can call this only
   * once a check has passed (or been explicitly bypassed), without
   * duplicating the streaming/diff/error-handling logic. */
  function runRegeneration(config: TripConfig) {
    const oldDays = useItineraryStore.getState().days
    // Capture the outgoing generation's id before it's overwritten below —
    // this regeneration is exactly the "regenerated" implicit-quality
    // signal (docs/rag-strategy.md's Learning Flywheel), reported against
    // the plan being replaced, not the new one.
    const outgoingGenerationId = useItineraryStore.getState().generationId
    setRegenNote('Updating your itinerary…')

    cancelRegenRef.current?.()
    cancelRegenRef.current = streamItinerary(
      { ...config, pace: useTripConfigStore.getState().effectivePace() },
      (msg) => setRegenNote(msg || 'Updating your itinerary…'),
      (result) => {
        sendGenerationSignal(outgoingGenerationId, 'regenerated')
        useItineraryStore.getState().setDays(
          result.days,
          result.alignment_score,
          result.expense_breakdown,
          result.generation_tier,
          result.warnings,
          result.generation_id,
        )
        setRegenNote(null)
        const diff = diffItineraries(oldDays, result.days)
        addMessage(
          isEmptyDiff(diff)
            ? { role: 'assistant', content: '✅ Itinerary refreshed — same plan, no visible changes.' }
            : { role: 'assistant', content: "✅ Done! Here's what changed in your itinerary:", diff },
        )
      },
      (code, message) => {
        setRegenNote(null)
        // Bug fix: this used to ignore `code` entirely and always show a
        // generic "couldn't update" error — including on AUTH_REQUIRED
        // (session expired/never established mid-refine). That silently
        // dead-ended the user with no way back to sign-in, unlike the
        // initial-generation path in LLMWizard.tsx which saves the pending
        // config and redirects to /signup. Mirror that same recovery here:
        // save the config, open the wizard so LLMWizard's existing
        // resume-after-auth effect can pick it up and regenerate
        // automatically, then send the user to sign in.
        if (code === 'AUTH_REQUIRED') {
          savePendingGeneration(config)
          addMessage({
            role: 'assistant',
            content: "You'll need to sign in again to save this change — taking you there now, then I'll pick up right where we left off.",
          })
          useAppStore.getState().openWizard()
          router.push(`/signup?returnTo=${encodeURIComponent('/')}`)
          return
        }
        addMessage({
          role: 'assistant',
          content: `⚠️ I couldn't update the itinerary (${message}). Your current plan is untouched — try again in a moment.`,
        })
      },
    )
  }

  /** Regenerate the itinerary in place with the (already-updated) config,
   * verifying the destination exists and the budget still covers the trip
   * first — mirrors LLMWizard's initial-generation feasibility gate,
   * including the destination-existence check (⭐ NEW — this was the one
   * entry point where a destination edit landed on the itinerary page with
   * no check at all, since only the initial-generation wizard flow had it).
   * No "proceed anyway" bypass for budget infeasibility: the only ways
   * forward are raising it, viewing the breakdown to decide what to cut, or
   * keeping the current itinerary. The destination check DOES allow an
   * explicit override — same high-false-negative-rate reasoning as
   * LLMWizard's CONTINUE_ANYWAY_CHIP. */
  async function regenerateInPlace(config: TripConfig, skipDestinationCheck = false) {
    try {
      const result = await checkFeasibility(config, skipDestinationCheck)
      if (result.destination_verified === false) {
        addMessage({
          role: 'assistant',
          content: `${result.verdict} Your current itinerary is untouched — you can confirm it's a real place and continue, or tell me the right destination.`,
        })
        setPendingFeasibility({ config, kind: 'destination_unverified', result })
        return
      }
      if (result.feasible) {
        runRegeneration(config)
        return
      }
      const minBudget = suggestedFeasibleBudget(result)
      const breakdownText = formatFeasibilityBreakdown(result)
      addMessage({
        role: 'assistant',
        content: `${result.verdict} Breakdown: ${breakdownText}. This is a bare-minimum estimate (activities/shopping extra). Your current itinerary is untouched — increase the budget to around ₹${minBudget.toLocaleString('en-IN')}, see the full breakdown to decide what to cut, or keep what you have.`,
      })
      setPendingFeasibility({ config, kind: 'infeasible', result, suggestedBudget: minBudget })
    } catch {
      // Feasibility check itself failed (network/server) — this used to
      // fall straight through to streamItinerary with no check at all,
      // the same "generated anyway" bug the initial-generation gate fixed.
      // Stop here instead: no regeneration until the user says how to
      // proceed.
      addMessage({
        role: 'assistant',
        content: "I couldn't verify whether this still fits your budget just now (a connection hiccup on my end) — I won't regenerate without checking. Your current itinerary is untouched.",
      })
      setPendingFeasibility({ config, kind: 'error' })
    }
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || status === 'sending' || regenNote) return

    setInput('')
    addMessage({ role: 'user', content: text })

    // "Show me my last itinerary" / "continue my trip" (issue #65) —
    // authenticated users only, checked here (not left to the backend
    // 401) so a guest never even sees the attempt disclosed in the chat.
    if (RESUME_LAST_ITINERARY_INTENT.test(text) && useAuthStore.getState().status === 'authenticated') {
      addMessage({ role: 'assistant', content: '…' })
      setStatus('sending')
      const resumed = await loadLastItinerary()
      if (resumed) {
        useChatStore.getState().updateLastAssistant(
          `Found it — here's your ${resumed.destination} trip, loaded back in for you to keep editing.`,
        )
      } else {
        useChatStore.getState().updateLastAssistant(
          "I don't have a saved trip to bring back yet — generate one and I'll remember it for next time.",
        )
      }
      setStatus('idle')
      return
    }

    addMessage({ role: 'assistant', content: '…' })
    setStatus('sending')

    try {
      const history = useChatStore.getState().messages.slice(0, -1).map((m) => ({
        role: m.role,
        content: m.content,
      }))
      const result = await chatRefine(history, tripConfig)
      // Every chat turn while an itinerary is on screen is engagement with
      // it — the "post_gen_chat_turns" implicit-quality signal
      // (docs/rag-strategy.md's Learning Flywheel). Reported against
      // whichever generation is current *before* this turn potentially
      // triggers a regeneration below, since the turn itself was about the
      // plan the user was looking at when they sent it.
      if (useItineraryStore.getState().days.length > 0) {
        sendGenerationSignal(useItineraryStore.getState().generationId, 'chat_turn')
      }
      useChatStore.getState().updateLastAssistant(
        result.reply,
        result.pinned_pois?.length ? { pins: result.pinned_pois } : undefined,
      )
      setStatus('idle')

      if (result.action_type === 'patch_config' && result.config_patch) {
        updateConfig(result.config_patch as Parameters<typeof updateConfig>[0])
        // Newly pinned places are a commitment — regenerate the plan around
        // them right away (if one exists) and show the diff. A per-day spend
        // change ("make day 3 cheaper") is the same kind of edit: the user
        // asked for the itinerary itself to change, so applying it silently
        // to the config and waiting for some later regeneration is exactly
        // the "promised an edit that never happens" bug this path fixes.
        const rebuilds =
          result.config_patch.pinned_pois || result.config_patch.day_cost_preferences
        if (rebuilds && useItineraryStore.getState().days.length > 0) {
          regenerateInPlace(useTripConfigStore.getState().config)
        }
      } else if (result.action_type === 'regenerate' && result.major_change) {
        setPendingAction(result)
      }
    } catch {
      useChatStore.getState().updateLastAssistant(
        "Sorry, I couldn't connect right now. Please try again."
      )
      setStatus('error', 'Connection failed')
    }
  }

  function handleConfirmRegenerate() {
    if (!pendingAction?.config_patch) { setPendingAction(null); return }
    updateConfig(pendingAction.config_patch as Parameters<typeof updateConfig>[0])
    setPendingAction(null)
    if (useItineraryStore.getState().days.length > 0) {
      addMessage({ role: 'assistant', content: '✅ Got it! Rebuilding your itinerary with the new settings…' })
      regenerateInPlace(useTripConfigStore.getState().config)
    } else {
      addMessage({
        role: 'assistant',
        content: "✅ Got it! I've updated your trip settings — generate an itinerary whenever you're ready.",
      })
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-x-4 bottom-4 z-[9998] flex w-auto flex-col overflow-hidden rounded-2xl border border-[var(--_border)] bg-[var(--_card)] shadow-2xl sm:left-auto sm:right-6 sm:bottom-24 sm:w-[360px]"
      style={{ maxHeight: '540px' }}
    >
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-[var(--_border)] bg-[var(--_primary)] px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white/20">
            <span className="text-sm">✈️</span>
          </div>
          <div>
            <p className="text-sm font-semibold text-white">Anya</p>
            {/* Says the job, not the persona. This was "Your AI travel
                concierge" — word for word what the wizard's header also said,
                so once either was open nothing distinguished them. The split
                that matters is who asks: the wizard questions you through a
                setup, here you question it about the plan on screen. */}
            <p className="text-xs text-white/70">Ask &amp; adjust</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <ThemeToggle className="flex h-7 w-7 items-center justify-center rounded-lg text-white/70 transition-colors hover:text-white" />
          <button
            onClick={close}
            className="text-white/70 transition-colors hover:text-white"
            aria-label="Close Anya chat"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {messages.length === 0 && (
          <div className="flex gap-2">
            <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--_primary)]">
              <span className="text-xs text-white">✈</span>
            </div>
            <div className="max-w-[80%] rounded-2xl rounded-bl-sm bg-[var(--_card-elevated)] px-3 py-2 text-sm leading-relaxed text-[var(--_fg)]">
              {WELCOME.split('\n').map((line, i) => (
                <span key={i}>{line}{i < WELCOME.split('\n').length - 1 && <br />}</span>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        {status === 'sending' && messages.at(-1)?.content === '…' && (
          <div className="flex items-center gap-1 pl-8">
            {['-0.3s', '-0.15s', '0s'].map((d) => (
              <span
                key={d}
                className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--_muted-fg)]"
                style={{ animationDelay: d }}
              />
            ))}
          </div>
        )}

        {regenNote && (
          <div className="mx-1 flex items-center gap-2 rounded-xl border border-[var(--_border)] bg-[var(--_card-elevated)] px-3 py-2">
            <RefreshCw size={13} className="animate-spin text-[var(--_primary)]" />
            <span className="text-xs text-[var(--_muted-fg)]">{regenNote}</span>
          </div>
        )}

        {pendingAction && (
          <div className="mx-1 space-y-2 rounded-xl border border-[var(--_warning,#F59E0B)]/40 bg-amber-50 p-3 dark:bg-amber-950/30">
            <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">
              ⚠️ This change will regenerate your itinerary
            </p>
            <div className="flex gap-2">
              <button
                onClick={handleConfirmRegenerate}
                className="flex-1 rounded-lg bg-[var(--_primary)] py-1.5 text-xs font-semibold text-white hover:opacity-90"
              >
                Yes, rebuild it
              </button>
              <button
                onClick={() => setPendingAction(null)}
                className="flex-1 rounded-lg border border-[var(--_border)] py-1.5 text-xs font-semibold text-[var(--_fg)] hover:bg-[var(--_card-elevated)]"
              >
                Just noting it
              </button>
            </div>
          </div>
        )}

        {pendingFeasibility && (
          <div className="mx-1 space-y-2 rounded-xl border border-[var(--_warning,#F59E0B)]/40 bg-amber-50 p-3 dark:bg-amber-950/30">
            <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">
              {pendingFeasibility.kind === 'error'
                ? "⚠️ Couldn't verify this budget still fits"
                : pendingFeasibility.kind === 'destination_unverified'
                  ? "⚠️ We couldn't verify this destination"
                  : '⚠️ This budget may not cover the trip'}
            </p>
            {pendingFeasibility.kind === 'destination_unverified' ? (
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    const cfg = pendingFeasibility.config
                    setPendingFeasibility(null)
                    regenerateInPlace(cfg, true)
                  }}
                  className="flex-1 rounded-lg bg-[var(--_primary)] py-1.5 text-xs font-semibold text-white hover:opacity-90"
                >
                  It&apos;s real, continue anyway
                </button>
                <button
                  onClick={() => {
                    setPendingFeasibility(null)
                    addMessage({ role: 'assistant', content: "No problem — what's the correct destination?" })
                  }}
                  className="flex-1 rounded-lg border border-[var(--_border)] py-1.5 text-xs font-semibold text-[var(--_fg)] hover:bg-[var(--_card-elevated)]"
                >
                  Let me fix it
                </button>
              </div>
            ) : pendingFeasibility.kind === 'error' ? (
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    const cfg = pendingFeasibility.config
                    setPendingFeasibility(null)
                    regenerateInPlace(cfg)
                  }}
                  className="flex-1 rounded-lg bg-[var(--_primary)] py-1.5 text-xs font-semibold text-white hover:opacity-90"
                >
                  Retry check
                </button>
                <button
                  onClick={() => {
                    setPendingFeasibility(null)
                    addMessage({ role: 'assistant', content: 'Okay — keeping your current itinerary as-is.' })
                  }}
                  className="flex-1 rounded-lg border border-[var(--_border)] py-1.5 text-xs font-semibold text-[var(--_fg)] hover:bg-[var(--_card-elevated)]"
                >
                  Keep current itinerary
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <button
                  onClick={() => {
                    const cfg = pendingFeasibility.config
                    const minBudget = pendingFeasibility.suggestedBudget
                    if (minBudget == null) return
                    const updatedConfig: TripConfig = { ...cfg, budget: { ...cfg.budget, amount: minBudget } }
                    updateConfig({ budget: updatedConfig.budget })
                    setPendingFeasibility(null)
                    addMessage({
                      role: 'assistant',
                      content: `Updated budget to ₹${minBudget.toLocaleString('en-IN')} — rebuilding your itinerary…`,
                    })
                    regenerateInPlace(updatedConfig)
                  }}
                  className="rounded-lg bg-[var(--_primary)] py-1.5 text-xs font-semibold text-white hover:opacity-90"
                >
                  Set budget to ₹{pendingFeasibility.suggestedBudget?.toLocaleString('en-IN')}
                </button>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      if (pendingFeasibility.result) {
                        addMessage({
                          role: 'assistant',
                          content: formatFeasibilityBreakdownDetailed(pendingFeasibility.result),
                        })
                      }
                    }}
                    className="flex-1 rounded-lg border border-[var(--_border)] py-1.5 text-xs font-semibold text-[var(--_fg)] hover:bg-[var(--_card-elevated)]"
                  >
                    Show budget breakdown
                  </button>
                  <button
                    onClick={() => {
                      setPendingFeasibility(null)
                      addMessage({ role: 'assistant', content: 'Okay — keeping your current itinerary as-is.' })
                    }}
                    className="flex-1 rounded-lg border border-[var(--_border)] py-1.5 text-xs font-semibold text-[var(--_fg)] hover:bg-[var(--_card-elevated)]"
                  >
                    Keep current itinerary
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {errorMsg && (
        <div className="shrink-0 border-t border-red-100 bg-red-50 px-3 py-1.5 text-xs text-red-600 dark:border-red-900 dark:bg-red-950/40 dark:text-red-400">
          ⚠️ {errorMsg}
        </div>
      )}

      {/* Input */}
      <div className="shrink-0 border-t border-[var(--_border)] bg-[var(--_card)] px-3 py-2.5">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your trip or request changes…"
            maxLength={MAX_CHAT_MESSAGE_LEN}
            rows={1}
            disabled={status === 'sending' || regenNote !== null}
            className="max-h-24 flex-1 resize-none overflow-y-auto rounded-xl border border-[var(--_border)] bg-[var(--_bg)] px-3 py-2 text-sm leading-snug text-[var(--_fg)] placeholder:text-[var(--_muted-fg)] focus:border-[var(--_primary)] focus:outline-none disabled:opacity-50"
            style={{ scrollbarWidth: 'none' }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || status === 'sending' || regenNote !== null}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--_primary)] text-white transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Send message"
          >
            <Send size={15} />
          </button>
        </div>
        <p className="mt-1.5 text-center text-xs text-[var(--_muted-fg)]">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}
