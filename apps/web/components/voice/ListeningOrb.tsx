'use client'

interface ListeningOrbProps {
  isActive: boolean
  isRecording: boolean
  className?: string
  /**
   * Tailwind width/height for the SVG. Defaults to the original fixed 72px.
   *
   * Sizing moved from `width`/`height` attributes to classes so a caller can
   * scale it per breakpoint from one element — the `viewBox` does the rest.
   * The alternative, rendering two orbs behind `lg:hidden`/`hidden lg:block`,
   * would run both breathing animations at once for the life of the page.
   */
  svgClassName?: string
}

export function ListeningOrb({
  isActive,
  isRecording,
  className = '',
  svgClassName = 'h-[72px] w-[72px]',
}: ListeningOrbProps) {
  return (
    <div className={`listening-orb-container inline-flex flex-col items-center justify-center gap-2 ${className}`}>
      <div className="relative flex items-center justify-center">
        <svg
          viewBox="0 0 72 72"
          className={`${svgClassName} ${isActive ? 'orb-active' : 'orb-idle'}`}
        >
          {/* Main breathing circle */}
          <circle
            cx="36"
            cy="36"
            r="30"
            fill="url(#orbGradient)"
            className="transition-all duration-300"
          />

          {/* Gradient definition */}
          <defs>
            <linearGradient id="orbGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" style={{ stopColor: 'var(--color-accent)' }} />
              <stop offset="100%" style={{ stopColor: 'var(--color-primary)' }} />
            </linearGradient>
            <radialGradient id="pulseGradient" cx="50%" cy="50%" r="50%">
              <stop offset="0%" style={{ stopColor: 'var(--color-accent)', stopOpacity: 0.6 }} />
              <stop offset="100%" style={{ stopColor: 'var(--color-accent)', stopOpacity: 0 }} />
            </radialGradient>
          </defs>

          {/* Pulse rings (only when active) */}
          {isActive && (
            <>
              <circle
                cx="36"
                cy="36"
                r="36"
                fill="none"
                stroke="var(--color-accent)"
                strokeWidth="2"
                opacity="0.4"
                className="pulse-ring"
              />
              <circle
                cx="36"
                cy="36"
                r="42"
                fill="none"
                stroke="var(--color-accent)"
                strokeWidth="1"
                opacity="0.2"
                className="pulse-ring-delayed"
              />
            </>
          )}

          {/* Microphone icon overlay */}
          <g transform="translate(36, 36)">
            <path
              d="M-6,-8 L-6,2 C-6,5.314 -3.314,8 0,8 C3.314,8 6,5.314 6,2 L6,-8 C6,-11.314 3.314,-14 0,-14 C-3.314,-14 -6,-11.314 -6,-8 Z"
              fill="white"
              opacity="0.9"
            />
            <path
              d="M-10,2 C-10,7.523 -5.523,12 0,12 C5.523,12 10,7.523 10,2"
              stroke="white"
              strokeWidth="2"
              fill="none"
              opacity="0.9"
              strokeLinecap="round"
            />
            <line
              x1="0"
              y1="12"
              x2="0"
              y2="18"
              stroke="white"
              strokeWidth="2"
              opacity="0.9"
              strokeLinecap="round"
            />
          </g>
        </svg>

        {isRecording && (
          <div
            role="status"
            aria-live="polite"
            className="absolute -bottom-2 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-[var(--_success)] bg-[var(--_card)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--_success)] shadow-sm"
          >
            <span className="h-2.5 w-2.5 rounded-full bg-[var(--_success)] motion-safe:animate-pulse motion-reduce:animate-none" />
            Listening
          </div>
        )}
      </div>

      <style>{`
        @keyframes breathe {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.05); }
        }

        @keyframes breatheFast {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.08); }
        }

        @keyframes pulse {
          0% {
            opacity: 0.6;
            transform: scale(0.9);
          }
          100% {
            opacity: 0;
            transform: scale(1.4);
          }
        }

        @media (prefers-reduced-motion: no-preference) {
          .orb-idle circle:first-child {
            animation: breathe 3s ease-in-out infinite;
          }

          .orb-active circle:first-child {
            animation: breatheFast 1s ease-in-out infinite;
          }

          .pulse-ring {
            animation: pulse 2s ease-out infinite;
            transform-origin: center;
          }

          .pulse-ring-delayed {
            animation: pulse 2s ease-out infinite;
            animation-delay: 1s;
            transform-origin: center;
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .orb-idle circle:first-child,
          .orb-active circle:first-child,
          .pulse-ring,
          .pulse-ring-delayed {
            animation: none;
          }

          .orb-active circle:first-child {
            transform: scale(1.03);
          }

          .pulse-ring {
            opacity: 0.28;
          }

          .pulse-ring-delayed {
            opacity: 0.18;
          }
        }
      `}</style>
    </div>
  )
}
