interface Props {
  size?: 'sm' | 'md' | 'lg'
  /** On dark background: brighter gold + gold wordmark.
   *  On light background (default): warmer gold + navy wordmark. */
  inverted?: boolean
  /** Show wordmark alongside the icon (default: true) */
  wordmark?: boolean
}

// Icon viewBox is 72 × 58 (W mark aspect ratio ~1.24 : 1)
const SIZES = {
  sm: { h: 28,  w: 35,  text: 'text-sm',   tagText: 'text-[0.45rem]', gap: 'gap-2'   },
  md: { h: 36,  w: 45,  text: 'text-base', tagText: 'text-[0.55rem]', gap: 'gap-2.5' },
  lg: { h: 48,  w: 60,  text: 'text-lg',   tagText: 'text-[0.6rem]',  gap: 'gap-3'   },
}

/**
 * Wanderplanner brand mark — inspired by the geometric W logo.
 *
 * W construction (viewBox 0 0 72 58):
 *  5-point W:  TL(6,6) → BL(18,50) → IT(34,8) → BR(50,50) → TR(62,6)
 *  + cross-diagonal 1: TL(6,6)  → BR(50,50)  — creates left diamond node @ (27,27)
 *  + cross-diagonal 2: BL(18,50) → TR(62,6)   — creates right diamond node @ (41,27)
 *  + compass arrow at TR tip pointing NE
 *
 * Colours:
 *  inverted (dark bg) : bright metallic gold mark + gold wordmark
 *  normal  (light bg) : warm muted gold mark + dark-navy wordmark
 */
export function WanderplannerLogo({ size = 'md', inverted = false, wordmark = true }: Props) {
  const { h, w, text, tagText, gap } = SIZES[size]

  // Gold palette — brighter on dark, richer/warmer on light
  const gA = inverted ? '#F5D060' : '#A8820A'   // gradient start
  const gB = inverted ? '#D4AF37' : '#C9A227'   // gradient mid / node fill
  const gC = inverted ? '#B89020' : '#DFB84A'   // gradient end
  const wordmarkClr = inverted ? '#E8C060' : '#0C4A6E'
  const taglineClr  = inverted ? '#D4AF3799' : '#64748B'

  // Unique-per-size gradient ID (at most one of each size on any page)
  const gId = `wp-gold-${size}`
  const sw  = size === 'lg' ? 2 : 1.6   // stroke width

  // Diamond node radius scales with stroke width
  const nr = sw + 1.2

  return (
    <span className={`inline-flex select-none items-center ${gap}`}>

      {/* ── W mark ───────────────────────────────────────────────── */}
      <svg
        width={w}
        height={h}
        viewBox="0 0 72 58"
        fill="none"
        aria-hidden="true"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          {/* Gradient spans the full W from TL to BR */}
          <linearGradient id={gId} x1="6" y1="6" x2="62" y2="50" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stopColor={gA}/>
            <stop offset="50%"  stopColor={gB}/>
            <stop offset="100%" stopColor={gC}/>
          </linearGradient>
        </defs>

        {/* ── W outline (4 segments) ── */}
        <path
          d="M6 6 L18 50 L34 8 L50 50 L62 6"
          stroke={`url(#${gId})`}
          strokeWidth={sw}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* ── Cross-diagonals — create the diamond intersections ── */}
        {/* Diag 1: TL → BR (crosses left inner arm at ~27,27) */}
        <line x1="6"  y1="6"  x2="50" y2="50" stroke={`url(#${gId})`} strokeWidth={sw} strokeLinecap="round"/>
        {/* Diag 2: BL → TR (crosses right inner arm at ~41,27) */}
        <line x1="18" y1="50" x2="62" y2="6"  stroke={`url(#${gId})`} strokeWidth={sw} strokeLinecap="round"/>

        {/* ── Diamond node markers (filled circles at intersections) ── */}
        <circle cx="27" cy="27" r={nr} fill={gB}/>
        <circle cx="41" cy="27" r={nr} fill={gB}/>
        {/* Inner-peak node at W top */}
        <circle cx="34" cy="8"  r={nr - 0.8} fill={gB}/>

        {/* ── Compass arrow at TR(62,6) — pointing NE ── */}
        <path
          d="M62 6 L69 0"
          stroke={gB}
          strokeWidth={sw - 0.2}
          strokeLinecap="round"
        />
        {/* Arrowhead */}
        <path
          d="M69 0 L65 2 M69 0 L67 5"
          stroke={gB}
          strokeWidth={sw - 0.3}
          strokeLinecap="round"
        />
      </svg>

      {/* ── Wordmark ─────────────────────────────────────────────── */}
      {wordmark && (
        <span className="flex flex-col leading-none">
          <span
            className={`font-display font-bold tracking-[0.14em] ${text}`}
            style={{ color: wordmarkClr, fontFamily: 'var(--font-space-grotesk)' }}
          >
            WANDERPLANNER
          </span>
          {size !== 'sm' && (
            <span
              className={`mt-[3px] tracking-[0.18em] font-medium uppercase ${tagText}`}
              style={{ color: taglineClr, fontFamily: 'var(--font-dm-sans)', letterSpacing: '0.18em' }}
            >
              Curated AI Travel Planning
            </span>
          )}
        </span>
      )}
    </span>
  )
}

