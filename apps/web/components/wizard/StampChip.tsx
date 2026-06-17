'use client'

interface StampChipProps {
  label: string
  isSelected?: boolean
  onClick: () => void
}

export function StampChip({ label, isSelected, onClick }: StampChipProps) {
  const rotation = Math.random() * 4 - 2 // Random rotation between -2 and +2 degrees

  return (
    <button
      type="button"
      onClick={onClick}
      className={`stamp-chip ${isSelected ? 'stamp-chip-selected' : ''}`}
      style={{ transform: `rotate(${rotation}deg)` }}
    >
      <span className="stamp-chip-label">{label}</span>
      
      <style jsx>{`
        .stamp-chip {
          position: relative;
          padding: 8px 16px;
          background: #F7F4EF;
          border: 2px dashed #B85C3F;
          border-radius: 2px;
          font-family: var(--font-mono);
          font-size: 13px;
          font-weight: 600;
          color: #1A3A52;
          transition: all 0.2s;
          cursor: pointer;
          overflow: hidden;
        }

        .stamp-chip::before {
          content: '';
          position: absolute;
          inset: 0;
          background: 
            repeating-linear-gradient(
              90deg,
              transparent,
              transparent 3px,
              rgba(26, 58, 82, 0.03) 3px,
              rgba(26, 58, 82, 0.03) 6px
            );
          pointer-events: none;
        }

        .stamp-chip:hover {
          transform: rotate(0deg) scale(1.05) !important;
          border-color: #E88D3A;
          box-shadow: 0 4px 12px rgba(232, 141, 58, 0.2);
          background: #FFFDF9;
        }

        .stamp-chip-selected {
          background: #E88D3A;
          border-color: #B85C3F;
          border-style: solid;
          color: white;
          box-shadow: 0 2px 8px rgba(232, 141, 58, 0.3);
        }

        .stamp-chip-selected::before {
          background: 
            repeating-linear-gradient(
              90deg,
              transparent,
              transparent 3px,
              rgba(255, 255, 255, 0.1) 3px,
              rgba(255, 255, 255, 0.1) 6px
            );
        }

        .stamp-chip-selected:hover {
          background: #D97706;
        }

        .stamp-chip-label {
          position: relative;
          z-index: 1;
        }
      `}</style>
    </button>
  )
}
