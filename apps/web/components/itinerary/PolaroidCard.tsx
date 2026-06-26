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

  const imageContent = (
    <div
      className="relative w-full overflow-hidden rounded-t-md"
      style={{ aspectRatio: '16/9', background: imageSrc ? undefined : gradient }}
    >
      {imageSrc && (
        <img
          src={imageSrc}
          alt={title}
          className="h-full w-full object-cover"
          loading="lazy"
        />
      )}
      {/* Scrim for readability on images */}
      {imageSrc && <div className="absolute inset-0 bg-gradient-to-t from-black/30 to-transparent" />}
      {category && (
        <span className="absolute right-2 top-2 rounded bg-white/95 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-[var(--_ocean)] dark:bg-slate-900/90 dark:text-[var(--_primary)]">
          {category}
        </span>
      )}
    </div>
  )

  return (
    <div
      onClick={onClick}
      className={[
        'group cursor-pointer overflow-hidden rounded-xl border bg-[var(--_card)] shadow-sm transition-all duration-200',
        'hover:-translate-y-0.5 hover:shadow-md',
        isActive
          ? 'border-[var(--_primary)] shadow-[0_0_0_2px_var(--_primary)]'
          : 'border-[var(--_border)]',
      ].join(' ')}
    >
      {/* Image area — clickable to video if href exists */}
      {videoHref ? (
        <a
          href={videoHref}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="block"
        >
          {imageContent}
          {/* Play badge overlay */}
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-red-600/90 text-white shadow-lg">
              <svg viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5 pl-0.5"><path d="M8 5v14l11-7z"/></svg>
            </span>
          </div>
        </a>
      ) : (
        imageContent
      )}

      {/* Caption */}
      <div className="px-3 pb-3 pt-2">
        <span className="font-mono text-[11px] font-semibold text-[var(--_primary)]">{time}</span>
        <h3 className="mt-0.5 text-sm font-semibold leading-snug text-[var(--_fg)]">{title}</h3>
        <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-[var(--_muted-fg)]">{description}</p>
      </div>
    </div>
  )
}
