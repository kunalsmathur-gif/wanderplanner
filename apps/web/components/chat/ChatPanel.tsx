'use client'

import { useEffect, useRef, useState } from 'react'
import { X, Send, RefreshCw } from 'lucide-react'
import { useChatStore } from '@/store/chatStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { chatRefine, streamItinerary } from '@/lib/api'
import { diffItineraries, isEmptyDiff } from '@/lib/itineraryDiff'
import { ChatMessage } from './ChatMessage'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import type { ChatRefineResponse, TripConfig } from '@/types'

const WELCOME =
  "Hi! I'm Anya ✈️\n\nAsk me anything about your trip, or tell me to change your destination, dates, budget, or preferences and I'll update your plan!"

export function ChatPanel() {
  const { isOpen, close, messages, status, errorMsg, addMessage, setStatus } = useChatStore()
  const tripConfig = useTripConfigStore((s) => s.config)
  const updateConfig = useTripConfigStore((s) => s.updateConfig)

  const [input, setInput] = useState('')
  const [pendingAction, setPendingAction] = useState<ChatRefineResponse | null>(null)
  const [regenNote, setRegenNote] = useState<string | null>(null)
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

  /** Regenerate the itinerary in place with the (already-updated) config and
   * post a visible diff of what changed as chips in the chat. The old
   * itinerary stays on screen until the new one lands — a failed refinement
   * never destroys a working plan. */
  function regenerateInPlace(config: TripConfig) {
    const oldDays = useItineraryStore.getState().days
    setRegenNote('Updating your itinerary…')

    cancelRegenRef.current?.()
    cancelRegenRef.current = streamItinerary(
      { ...config, pace: useTripConfigStore.getState().effectivePace() },
      (msg) => setRegenNote(msg || 'Updating your itinerary…'),
      (result) => {
        useItineraryStore.getState().setDays(
          result.days,
          result.alignment_score,
          result.expense_breakdown,
        )
        setRegenNote(null)
        const diff = diffItineraries(oldDays, result.days)
        addMessage(
          isEmptyDiff(diff)
            ? { role: 'assistant', content: '✅ Itinerary refreshed — same plan, no visible changes.' }
            : { role: 'assistant', content: "✅ Done! Here's what changed in your itinerary:", diff },
        )
      },
      (_code, message) => {
        setRegenNote(null)
        addMessage({
          role: 'assistant',
          content: `⚠️ I couldn't update the itinerary (${message}). Your current plan is untouched — try again in a moment.`,
        })
      },
    )
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || status === 'sending' || regenNote) return

    setInput('')
    addMessage({ role: 'user', content: text })
    addMessage({ role: 'assistant', content: '…' })
    setStatus('sending')

    try {
      const history = useChatStore.getState().messages.slice(0, -1).map((m) => ({
        role: m.role,
        content: m.content,
      }))
      const result = await chatRefine(history, tripConfig)
      useChatStore.getState().updateLastAssistant(
        result.reply,
        result.pinned_pois?.length ? { pins: result.pinned_pois } : undefined,
      )
      setStatus('idle')

      if (result.action_type === 'patch_config' && result.config_patch) {
        updateConfig(result.config_patch as Parameters<typeof updateConfig>[0])
        // Newly pinned places are a commitment — regenerate the plan around
        // them right away (if one exists) and show the diff.
        if (result.config_patch.pinned_pois && useItineraryStore.getState().days.length > 0) {
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
      className="fixed bottom-24 right-6 z-[9998] flex w-[360px] flex-col overflow-hidden rounded-2xl border border-[var(--_border)] bg-[var(--_card)] shadow-2xl"
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
            <p className="text-xs text-white/70">Your AI travel concierge</p>
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
