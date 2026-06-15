'use client'

import type { ChatMessage as ChatMsg } from '@/store/chatStore'

interface Props {
  message: ChatMsg
}

export function ChatMessage({ message }: Props) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} gap-2`}>
      {!isUser && (
        <div className="w-6 h-6 rounded-full bg-[#1E40AF] flex items-center justify-center shrink-0 mt-0.5">
          <span className="text-white text-xs">✈</span>
        </div>
      )}
      <div
        className={[
          'max-w-[80%] rounded-2xl px-3 py-2 text-sm leading-relaxed',
          isUser
            ? 'bg-[#1E40AF] text-white rounded-br-sm'
            : 'bg-slate-100 text-slate-800 rounded-bl-sm',
        ].join(' ')}
      >
        {message.content.split('\n').map((line, i) => (
          <span key={i}>
            {line}
            {i < message.content.split('\n').length - 1 && <br />}
          </span>
        ))}
      </div>
      {isUser && (
        <div className="w-6 h-6 rounded-full bg-slate-200 flex items-center justify-center shrink-0 mt-0.5">
          <span className="text-slate-600 text-xs">👤</span>
        </div>
      )}
    </div>
  )
}
