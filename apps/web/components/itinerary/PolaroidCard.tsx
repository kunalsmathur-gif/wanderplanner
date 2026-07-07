'use client'

import { useMemo } from 'react'

interface PolaroidCardProps {
  time: string
  title: string
  description: string
  category?: string
  /** Real image URL (e.g. YouTube thumbnail). Falls back to gradient. */
  imageSrc?: string | null
  /** YouTube video link — opens on image click */
  videoHref?: string | null
  /** Override gradient (CSS string). Auto-generated from title if omitted. */
  imageGradient?: string
  isActive?: boolean
  onClick?: () => void
}

// Deterministic gradient per title — avoids random on each render
const GRADIENTS = [
  'linear-gradient(135deg,#0EA5E9 0%,#0C4A6E 100%)',
  'linear-gradient(135deg,#EA580C 0%,#9A3412 100%)',
  'linear-gradient(135deg,#0EA5E9 0%,#7C3AED 100%)',
  'linear-gradient(135deg,#059669 0%,#065F46 100%)',
  'linear-gradient(135deg,#D4AF37 0%,#A8820A 100%)',
  'linear-gradient(135deg,#DB2777 0%,#831843 100%)',
]

function pickGradient(seed: string) {
  let h = 0
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0
  return GRADIENTS[h % GRADIENTS.length]
}

export function PolaroidCard({
  time,
  title,
  description,
  category,
  imageSrc,
  videoHref,
  imageGradient,
  isActive,
  onClick,
}: PolaroidCardProps) {
  const gradient = useMemo(() => imageGradient ?? pickGradient(title), [imageGradient, title])

  // Small, fixed-size thumbnail (not a hero image) — keeps the focus on the
  // itinerary text and lets many activities be scanned at a glance instead
  // of one giant video-style card dominating the whole column.
  const thumbnail = (
    <div
      className="relative h-20 w-20 shrink-0 overflow-hidden rounded-lg sm:h-24 sm:w-24"
      style={{ background: imageSrc ? undefined : gradient }}
    >
      {imageSrc && (
        <img
          src={imageSrc}
          alt={title}
          className="h-full w-full object-cover"
          loading="lazy"
        />
      )}
      {videoHref && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/10 opacity-0 transition-opacity group-hover:opacity-100">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-red-600/90 text-white shadow">
            <svg viewBox="0 0 24 24" fill="currentColor" className="h-3 w-3 pl-0.5"><path d="M8 5v14l11-7z"/></svg>
          </span>
        </div>
      )}
    </div>
  )

  return (
    <div
      onClick={onClick}
      className={[
        'group flex cursor-pointer gap-3 overflow-hidden rounded-xl border bg-[var(--_card)] p-2.5 shadow-sm transition-all duration-200',
        'hover:shadow-md',
        isActive
          ? 'border-[var(--_primary)] shadow-[0_0_0_2px_var(--_primary)]'
          : 'border-[var(--_border)]',
      ].join(' ')}
    >
      {/* Thumbnail — clickable to video if href exists */}
      {videoHref ? (
        <a
          href={videoHref}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="block shrink-0"
        >
          {thumbnail}
        </a>
      ) : (
        thumbnail
      )}

      {/* Content */}
      <div className="min-w-0 flex-1 py-0.5">
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-[11px] font-semibold text-[var(--_primary)]">{time}</span>
          {category && (
            <span className="shrink-0 rounded bg-[var(--_muted)] px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-[var(--_muted-fg)]">
              {category}
            </span>
          )}
        </div>
        <h3 className="mt-0.5 truncate text-sm font-semibold leading-snug text-[var(--_fg)]">{title}</h3>
        <p className="mt-0.5 line-clamp-2 text-xs leading-relaxed text-[var(--_muted-fg)]">{description}</p>
      </div>
    </div>
  )
}
