'use client'

interface ListeningOrbProps {
  isActive: boolean
  isRecording: boolean
  className?: string
}

export function ListeningOrb({ isActive, isRecording, className = '' }: ListeningOrbProps) {
  return (
    <div className={`listening-orb-container relative flex items-center justify-center ${className}`}>
      <svg
        width="72"
        height="72"
        viewBox="0 0 72 72"
        className={isActive ? 'orb-active' : 'orb-idle'}
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
            <stop offset="0%" stopColor="#E88D3A" />
            <stop offset="100%" stopColor="#A8BFDB" />
          </linearGradient>
          <radialGradient id="pulseGradient" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#E88D3A" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#E88D3A" stopOpacity="0" />
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
              stroke="#E88D3A"
              strokeWidth="2"
              opacity="0.4"
              className="pulse-ring"
            />
            <circle
              cx="36"
              cy="36"
              r="42"
              fill="none"
              stroke="#E88D3A"
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

      {/* Recording indicator dot */}
      {isRecording && (
        <div className="absolute bottom-1 right-1 h-3 w-3 rounded-full bg-red-500 animate-pulse" />
      )}

      <style jsx>{`
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

      `}</style>
    </div>
  )
}
