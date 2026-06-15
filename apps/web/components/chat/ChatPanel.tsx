'use client'

import { useEffect, useRef, useState } from 'react'
import { useChatStore } from '@/store/chatStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { sendChatMessage } from '@/lib/api'
import { ChatMessage } from './ChatMessage'

const WELCOME: string =
  "Hi! I'm WanderPlan Assistant ✈️\n\nAsk me anything about your trip — destinations, visas, budgets, packing, or itinerary tips. I'm here to help!"

export function ChatPanel() {
  const { isOpen, close, messages, status, errorMsg, addMessage, setStatus } = useChatStore()
  const tripConfig = useTripConfigStore((s) => s.config)
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Scroll to bottom on new message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) setTimeout(() => inputRef.current?.focus(), 150)
  }, [isOpen])

  async function handleSend() {
    const text = input.trim()
    if (!text || status === 'sending') return

    setInput('')
    addMessage({ role: 'user', content: text })

    // Optimistic assistant placeholder
    addMessage({ role: 'assistant', content: '…' })
    setStatus('sending')

    try {
      // Build history from store messages (exclude optimistic placeholder)
      const history = useChatStore.getState().messages.slice(0, -1).map((m) => ({
        role: m.role,
        content: m.content,
      }))

      // Pass minimal trip context (destination + budget) for personalization
      const ctx = tripConfig.destination
        ? {
            destination: tripConfig.destination.city,
            origin: tripConfig.origin.city,
            budget_inr: tripConfig.budget.amount,
            dates: tripConfig.dates,
          }
        : undefined

      const reply = await sendChatMessage(history, ctx)

      // Replace placeholder with real reply
      useChatStore.getState().updateLastAssistant(reply)
      setStatus('idle')
    } catch {
      useChatStore.getState().updateLastAssistant(
        "Sorry, I couldn't connect right now. Please try again."
      )
      setStatus('error', 'Connection failed')
    }
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
      style={{ maxHeight: '520px' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-[#1E40AF] shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center">
            <span className="text-white text-sm">✈️</span>
          </div>
          <div>
            <p className="text-white text-sm font-semibold">WanderPlan Assistant</p>
            <p className="text-blue-200 text-xs">Travel questions only</p>
          </div>
        </div>
        <button
          onClick={close}
          className="text-white/70 hover:text-white transition-colors text-lg leading-none"
          aria-label="Close chat"
        >
          ✕
        </button>
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
        <div ref={bottomRef} />
      </div>

      {/* Error banner */}
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
            placeholder="Ask about destinations, visas, budget…"
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
          Press Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}
