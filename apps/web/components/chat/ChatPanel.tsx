'use client'

import { useEffect, useRef, useState } from 'react'
import { useChatStore } from '@/store/chatStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { chatRefine } from '@/lib/api'
import { ChatMessage } from './ChatMessage'
import type { ChatRefineResponse } from '@/types'

const WELCOME: string =
  "Hi! I'm WanderPlan Assistant ✈️\n\nAsk me anything about your trip — or ask me to change your destination, dates, budget, or preferences and I'll update your plan!"

export function ChatPanel() {
  const { isOpen, close, messages, status, errorMsg, addMessage, setStatus } = useChatStore()
  const tripConfig = useTripConfigStore((s) => s.config)
  const updateConfig = useTripConfigStore((s) => s.updateConfig)
  const resetItinerary = useItineraryStore((s) => s.reset)

  const [input, setInput] = useState('')
  const [pendingAction, setPendingAction] = useState<ChatRefineResponse | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (isOpen) setTimeout(() => inputRef.current?.focus(), 150)
  }, [isOpen])

  async function handleSend() {
    const text = input.trim()
    if (!text || status === 'sending') return

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
      useChatStore.getState().updateLastAssistant(result.reply)
      setStatus('idle')

      if (result.action_type === 'patch_config' && result.config_patch) {
        updateConfig(result.config_patch as Parameters<typeof updateConfig>[0])
        // No confirmation needed — minor change already done
      } else if (result.action_type === 'regenerate' && result.major_change) {
        // Surface confirmation dialog
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
    resetItinerary()
    addMessage({
      role: 'assistant',
      content: '✅ Got it! I\'ve updated your trip settings. Head back to the wizard to regenerate your itinerary.',
    })
    setPendingAction(null)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (!isOpen) return null

  const showWelcome = messages.length === 0

  return (
    <div
      className="fixed bottom-24 right-6 z-[9998] w-[360px] flex flex-col rounded-2xl shadow-2xl border border-slate-200 bg-white overflow-hidden"
      style={{ maxHeight: '540px' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-[#1E40AF] shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center">
            <span className="text-white text-sm">✈️</span>
          </div>
          <div>
            <p className="text-white text-sm font-semibold">WanderPlan Assistant</p>
            <p className="text-blue-200 text-xs">Travel questions · Itinerary refinement</p>
          </div>
        </div>
        <button
          onClick={close}
          className="text-white/70 hover:text-white transition-colors text-lg leading-none"
          aria-label="Close chat"
        >✕</button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 min-h-0">
        {showWelcome && (
          <div className="flex justify-start gap-2">
            <div className="w-6 h-6 rounded-full bg-[#1E40AF] flex items-center justify-center shrink-0 mt-0.5">
              <span className="text-white text-xs">✈</span>
            </div>
            <div className="max-w-[80%] rounded-2xl rounded-bl-sm bg-slate-100 text-slate-800 px-3 py-2 text-sm leading-relaxed">
              {WELCOME.split('\n').map((line, i) => (
                <span key={i}>{line}{i < WELCOME.split('\n').length - 1 && <br />}</span>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        {status === 'sending' && messages[messages.length - 1]?.content === '…' && (
          <div className="flex items-center gap-1 pl-8">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.3s]" />
            <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.15s]" />
            <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" />
          </div>
        )}

        {/* Regeneration confirmation card */}
        {pendingAction && (
          <div className="mx-1 p-3 bg-amber-50 border border-amber-200 rounded-xl space-y-2">
            <p className="text-xs font-semibold text-amber-800">⚠️ This change will regenerate your itinerary</p>
            <div className="flex gap-2">
              <button
                onClick={handleConfirmRegenerate}
                className="flex-1 py-1.5 rounded-lg bg-[#1E40AF] text-white text-xs font-semibold hover:bg-blue-800"
              >
                Yes, apply & reset
              </button>
              <button
                onClick={() => setPendingAction(null)}
                className="flex-1 py-1.5 rounded-lg border border-slate-300 text-slate-600 text-xs font-semibold hover:bg-slate-50"
              >
                No, just noting it
              </button>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {errorMsg && (
        <div className="px-3 py-1.5 bg-red-50 border-t border-red-100 text-xs text-red-600 shrink-0">
          ⚠️ {errorMsg}
        </div>
      )}

      {/* Input */}
      <div className="px-3 py-2.5 border-t border-slate-200 bg-white shrink-0">
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your trip or request changes…"
            rows={1}
            disabled={status === 'sending'}
            className="flex-1 resize-none border border-slate-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-[#1E40AF] disabled:bg-slate-50 leading-snug max-h-24 overflow-y-auto"
            style={{ scrollbarWidth: 'none' }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || status === 'sending'}
            className={[
              'w-9 h-9 rounded-xl flex items-center justify-center shrink-0 transition-all',
              input.trim() && status !== 'sending'
                ? 'bg-[#1E40AF] hover:bg-blue-800 text-white'
                : 'bg-slate-100 text-slate-400 cursor-not-allowed',
            ].join(' ')}
            aria-label="Send message"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
        <p className="text-xs text-slate-400 mt-1.5 text-center">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}
