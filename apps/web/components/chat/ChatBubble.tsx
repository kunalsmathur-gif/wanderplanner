'use client'

import { useChatStore } from '@/store/chatStore'
import { ChatPanel } from './ChatPanel'

export function ChatBubble() {
  const { isOpen, toggle, messages } = useChatStore()
  const unread = !isOpen && messages.length === 0 // show pulse only before first interaction

  return (
    <>
      {/* Chat panel — slides up above the bubble */}
      <ChatPanel />

      {/* Floating action button */}
      <button
        onClick={toggle}
        aria-label={isOpen ? 'Close travel assistant' : 'Open travel assistant'}
        className={[
          'fixed bottom-6 right-6 z-[9999] w-14 h-14 rounded-full shadow-lg',
          'flex items-center justify-center transition-all duration-200',
          'focus:outline-none focus:ring-2 focus:ring-[#1E40AF] focus:ring-offset-2',
          isOpen
            ? 'bg-slate-700 hover:bg-slate-800 rotate-0'
            : 'bg-[#1E40AF] hover:bg-blue-800',
        ].join(' ')}
      >
        {/* Pulse ring — shown only before first use */}
        {unread && !isOpen && (
          <span className="absolute inset-0 rounded-full bg-[#1E40AF] animate-ping opacity-40" />
        )}

        {isOpen ? (
          // Close icon
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        ) : (
          // Plane / chat icon
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            <path d="M8 10h8M8 14h5" />
          </svg>
        )}
      </button>
    </>
  )
}
