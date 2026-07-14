'use client'

interface Props {
  code?: string
  message?: string
  onRetry: () => void
  onBack: () => void
}

const ERROR_META: Record<string, { icon: string; title: string; hint: string }> = {
  LLM_TIMEOUT: {
    icon: '⏱️',
    title: 'Generation timed out',
    hint: 'The AI took too long to respond. This can happen during peak hours — please try again.',
  },
  LLM_ERROR: {
    icon: '🤖',
    title: 'AI generation failed',
    hint: 'Something went wrong on our side while generating your itinerary — please try again in a moment.',
  },
  NETWORK_ERROR: {
    icon: '📡',
    title: 'Connection lost',
    hint: 'Could not reach WanderPlanner. Check your internet connection and try again.',
  },
  NO_RESULTS: {
    icon: '🔍',
    title: 'No results found',
    hint: 'No activities matched your filters. Try broadening your destination or adjusting your group settings.',
  },
}

const DEFAULT_META = { icon: '⚠️', title: 'Something went wrong', hint: 'An unexpected error occurred.' }

export function ErrorState({ code = '', message, onRetry, onBack }: Props) {
  const meta = ERROR_META[code] ?? DEFAULT_META

  return (
    <div className="flex flex-col items-center justify-center h-full gap-5 px-8">
      <div className="text-5xl">{meta.icon}</div>
      <div className="text-center max-w-sm">
        <h2 className="text-xl font-bold text-[var(--_fg)]">{meta.title}</h2>
        <p className="text-sm text-[var(--_muted-fg)] mt-2 leading-relaxed">{message || meta.hint}</p>
        {code && <p className="text-xs text-[var(--_muted-fg)] mt-1 font-mono">Error code: {code}</p>}
      </div>
      <div className="flex gap-3">
        <button
          onClick={onRetry}
          className="px-5 py-2.5 bg-[var(--_primary)] text-[var(--_on-primary)] rounded-lg text-sm font-semibold hover:bg-[var(--_primary-hover)]"
        >
          Try again
        </button>
        <button
          onClick={onBack}
          className="px-5 py-2.5 border border-[var(--_border)] text-[var(--_fg-muted)] rounded-lg text-sm hover:border-[var(--_muted-fg)]"
        >
          ← Edit inputs
        </button>
      </div>
    </div>
  )
}
