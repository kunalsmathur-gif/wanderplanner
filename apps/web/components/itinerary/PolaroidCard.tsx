'use client'

import Image from 'next/image'
import { useMemo, useState } from 'react'

interface PolaroidCardProps {
  time: string
  title: string
  description: string
  category?: string
  /** Real image URL (e.g. YouTube thumbnail). Falls back to gradient. */
  imageSrc?: string | null
  /** Shows a play affordance when a related video exists. Also makes the
   * thumbnail itself a direct link to the video (see render below) — it
   * used to be nested inside the card's own onClick (map-select) button,
   * so clicking a video thumbnail just selected the map marker instead of
   * ever opening the video. */
  videoHref?: string | null
  /** Override gradient (CSS string). Auto-generated from title if omitted. */
  imageGradient?: string
  isActive?: boolean
  onClick?: () => void
  /** Small badge, top-right corner of the card — a quick, glanceable signal
   * for which places are Wanderplanner-verified vs. AI-recalled, without
   * reordering the (intentionally chronological) list of items. */
  verified?: boolean
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
  verified,
}: PolaroidCardProps) {
  const gradient = useMemo(() => imageGradient ?? pickGradient(title), [imageGradient, title])
  // Some YouTube thumbnail URLs 404 (deleted/restricted videos, shorts with
  // no mqdefault variant) — track that separately so we can fall back to
  // the gradient instead of showing a broken-image icon.
  const [imgFailed, setImgFailed] = useState(false)
  const showImage = Boolean(imageSrc) && !imgFailed

  // Small, fixed-size thumbnail (not a hero image) — keeps the focus on the
  // itinerary text and lets many activities be scanned at a glance instead
  // of one giant video-style card dominating the whole column.
  const thumbnail = (
    <div
      className="relative h-20 w-20 shrink-0 overflow-hidden rounded-lg sm:h-24 sm:w-24"
      style={{ background: showImage ? undefined : gradient }}
    >
      {showImage && (
        <Image
          src={imageSrc!}
          alt={title}
          fill
          sizes="(max-width: 640px) 80px, 96px"
          className="object-cover"
          onError={() => setImgFailed(true)}
        />
      )}
      {videoHref && (
        // Real anchor (not just a hover overlay) so the play icon actually
        // opens the video. It's rendered on top of the card's own
        // map-select click handler, so we stop propagation to avoid the
        // click also firing the card's onClick.
        <a
          href={videoHref}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Watch video: ${title}`}
          onClick={(e) => e.stopPropagation()}
          className="absolute inset-0 z-10 flex items-center justify-center bg-black/10 opacity-0 transition-opacity group-hover:opacity-100"
        >
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-red-600/90 text-white shadow">
            <svg viewBox="0 0 24 24" fill="currentColor" className="h-3 w-3 pl-0.5"><path d="M8 5v14l11-7z"/></svg>
          </span>
        </a>
      )}
    </div>
  )

  return (
    // Was a <button>, but a card with a video needs a real nested <a> link
    // for the play affordance (invalid/unreliable inside a <button>) — a
    // div with button semantics lets the thumbnail's anchor be a proper,
    // independently-clickable sibling instead of swallowed by the outer
    // click handler.
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick?.()
        }
      }}
      aria-label={`Show ${title} on the map`}
      className={[
        'group relative flex w-full cursor-pointer gap-3 overflow-hidden rounded-xl border bg-[var(--_card)] p-2.5 text-left shadow-sm transition-all duration-200',
        'hover:shadow-md',
        isActive
          ? 'border-[var(--_primary)] shadow-[0_0_0_2px_var(--_primary)]'
          : 'border-[var(--_border)]',
      ].join(' ')}
    >
      {verified === true && (
        <span
          title="Verified against Wanderplanner's destination research"
          // Bottom-right (not top-right) — top-right overlapped the
          // category tag chip (e.g. "CULTURE") rendered in the content
          // header on the same corner.
          className="absolute bottom-1.5 right-1.5 z-20 flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500 text-[9px] font-bold text-white shadow"
        >
          ✓
        </span>
      )}

      {thumbnail}

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
