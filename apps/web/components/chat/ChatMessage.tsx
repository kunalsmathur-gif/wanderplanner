'use client'

import type { ChatMessage as ChatMsg } from '@/store/chatStore'
import type { ItineraryDiff } from '@/lib/itineraryDiff'

interface Props {
  message: ChatMsg
}

function DiffChips({ diff }: { diff: ItineraryDiff }) {
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {diff.added.map((e) => (
        <span
          key={`a-${e.title}-${e.day}`}
          className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300"
        >
          + {e.title} (Day {e.day})
        </span>
      ))}
      {diff.removed.map((e) => (
        <span
          key={`r-${e.title}-${e.day}`}
          className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-medium text-rose-700 line-through dark:bg-rose-900/60 dark:text-rose-300"
        >
          − {e.title}
        </span>
      ))}
      {diff.moved.map((e) => (
        <span
          key={`m-${e.title}-${e.day}`}
          className="rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-700 dark:bg-sky-900/60 dark:text-sky-300"
        >
          ↷ {e.title} (Day {e.fromDay} → {e.day})
        </span>
      ))}
    </div>
  )
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
        {!isUser && message.pins && message.pins.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {message.pins.map((pin) => (
              <span
                key={pin.name}
                className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800 dark:bg-amber-900/60 dark:text-amber-300"
                title={`Verified via ${pin.verified_by === 'osm' ? 'OpenStreetMap' : 'Wikivoyage'}`}
              >
                📌 {pin.name}
              </span>
            ))}
          </div>
        )}
        {!isUser && message.diff && <DiffChips diff={message.diff} />}
      </div>
      {isUser && (
        <div className="w-6 h-6 rounded-full bg-slate-200 flex items-center justify-center shrink-0 mt-0.5">
          <span className="text-slate-600 text-xs">👤</span>
        </div>
      )}
    </div>
  )
}
