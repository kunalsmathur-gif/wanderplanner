interface Props {
  size?: 'sm' | 'md' | 'lg'
  /** Render on dark/coloured background — navy becomes white */
  inverted?: boolean
  /** Show wordmark alongside the icon (default: true) */
  wordmark?: boolean
}

// Icon renders as a landscape rectangle (64 × 44 viewBox)
const SIZES = {
  sm: { h: 28,  w: 41,  text: 'text-base', gap: 'gap-2'   },
  md: { h: 36,  w: 52,  text: 'text-xl',   gap: 'gap-2.5' },
  lg: { h: 48,  w: 70,  text: 'text-2xl',  gap: 'gap-3'   },
}

/**
 * Wanderplan brand mark.
 *
 * Icon anatomy:
 *  • Left  — AI neural node: navy circle hub with 4 orange radiating dots
 *  • Centre — Thick navy W-shaped route (road/journey path)
 *  • Right  — Location pin: navy teardrop, white ring, orange centre dot
 *
 * Design system: Space Grotesk wordmark · #0C4A6E navy · #EA580C orange · #0EA5E9 sky
 */
export function WanderplanLogo({ size = 'md', inverted = false, wordmark = true }: Props) {
  const { h, w, text, gap } = SIZES[size]

  // Semantic colour aliases — flip for inverted (white-bg → dark-bg)
  const navy   = inverted ? '#ffffff' : '#0C4A6E'
  const orange = '#EA580C'
  const sky    = inverted ? '#FB923C' : '#0EA5E9'  // pin centre accent
  const hub    = inverted ? '#0EA5E9' : '#ffffff'   // hub inner dot

  return (
    <span className={`inline-flex select-none items-center ${gap}`}>
      {/* ── Icon mark ────────────────────────────────────────────── */}
      <svg
        width={w}
        height={h}
        viewBox="0 0 64 44"
        fill="none"
        aria-hidden="true"
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* ── AI neural node (left) ────────────────────────────── */}
        {/* Radiating lines → orange satellite dots */}
        <line x1="10" y1="22" x2="3"  y2="13" stroke={orange} strokeWidth="1.3" strokeLinecap="round"/>
        <line x1="10" y1="22" x2="1"  y2="22" stroke={orange} strokeWidth="1.3" strokeLinecap="round"/>
        <line x1="10" y1="22" x2="3"  y2="31" stroke={orange} strokeWidth="1.3" strokeLinecap="round"/>
        <line x1="10" y1="22" x2="6"  y2="12" stroke={orange} strokeWidth="1.3" strokeLinecap="round"/>
        <circle cx="3"  cy="13" r="2"   fill={orange}/>
        <circle cx="1"  cy="22" r="2"   fill={orange}/>
        <circle cx="3"  cy="31" r="2"   fill={orange}/>
        <circle cx="6"  cy="12" r="2"   fill={orange}/>
        {/* Hub ring + inner dot */}
        <circle cx="10" cy="22" r="4"   fill={navy}/>
        <circle cx="10" cy="22" r="1.8" fill={hub}/>

        {/* ── W journey route ──────────────────────────────────── */}
        {/* Short connector from node to main path */}
        <line x1="10" y1="22" x2="14" y2="22" stroke={navy} strokeWidth="3.5" strokeLinecap="round"/>
        {/* Smooth W shape: down → up → down → up (road/route aesthetic) */}
        <path
          d="M 14 22
             C 15 34  18 40  21 38
             C 24 36  26 26  28 20
             C 30 14  32 12  34 18
             C 36 24  38 34  41 38
             C 44 42  48 38  50 28
             L 51 24"
          stroke={navy}
          strokeWidth="3.5"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* ── Location pin (right) ─────────────────────────────── */}
        {/* Teardrop body: smooth pin pointing down to meet W path */}
        <path
          d="M 44.5 11
             C 44.5 5.5  59.5 5.5  59.5 11
             C 59.5 16.5  52 25  52 25
             C 52 25  44.5 16.5  44.5 11 Z"
          fill={navy}
        />
        {/* White ring inside pin */}
        <circle cx="52" cy="11" r="3.8" fill="white"/>
        {/* Accent dot — sky/orange depending on bg */}
        <circle cx="52" cy="11" r="2"   fill={sky}/>
      </svg>

      {/* ── Wordmark ─────────────────────────────────────────────── */}
      {wordmark && (
        <span
          className={[
            'font-display font-bold tracking-tight',
            text,
            inverted ? 'text-white' : 'text-[#0C4A6E]',
          ].join(' ')}
        >
          Wanderplan
        </span>
      )}
    </span>
  )
}
