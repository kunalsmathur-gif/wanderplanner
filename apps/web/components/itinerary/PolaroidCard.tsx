'use client'

interface PolaroidCardProps {
  time: string
  title: string
  description: string
  category?: string
  imageGradient?: string
}

export function PolaroidCard({ 
  time, 
  title, 
  description, 
  category,
  imageGradient = 'linear-gradient(135deg, #E88D3A 0%, #B85C3F 100%)'
}: PolaroidCardProps) {
  const rotation = Math.random() * 2 - 1 // Random rotation between -1 and +1 degree

  return (
    <div className="polaroid-card" style={{ transform: `rotate(${rotation}deg)` }}>
      <div className="polaroid-photo" style={{ background: imageGradient }}>
        {category && (
          <span className="polaroid-category">{category}</span>
        )}
      </div>
      <div className="polaroid-caption">
        <span className="polaroid-time">{time}</span>
        <h3 className="polaroid-title">{title}</h3>
        <p className="polaroid-description">{description}</p>
      </div>

      <style jsx>{`
        .polaroid-card {
          background: white;
          padding: 12px;
          border-radius: 4px;
          box-shadow: var(--shadow-polaroid);
          transition: all 0.3s;
          margin-bottom: 16px;
        }

        .polaroid-card:hover {
          transform: rotate(0deg) translateY(-2px) !important;
          box-shadow: 0 8px 20px rgba(26, 58, 82, 0.2);
        }

        .polaroid-photo {
          width: 100%;
          aspect-ratio: 4/3;
          border-radius: 2px;
          margin-bottom: 12px;
          position: relative;
          overflow: hidden;
        }

        .polaroid-category {
          position: absolute;
          top: 8px;
          right: 8px;
          background: rgba(255, 255, 255, 0.95);
          padding: 4px 10px;
          border-radius: 2px;
          font-family: var(--font-mono);
          font-size: 11px;
          font-weight: 600;
          color: #1A3A52;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .polaroid-caption {
          padding: 0 4px;
        }

        .polaroid-time {
          font-family: var(--font-mono);
          font-size: 12px;
          color: #E88D3A;
          font-weight: 600;
          display: block;
          margin-bottom: 4px;
        }

        .polaroid-title {
          font-family: var(--font-display);
          font-size: 18px;
          font-weight: 700;
          color: #2C3338;
          margin: 0 0 6px 0;
          line-height: 1.3;
        }

        .polaroid-description {
          font-family: var(--font-body);
          font-size: 14px;
          line-height: 1.5;
          color: #6B7280;
          margin: 0;
        }
      `}</style>
    </div>
  )
}
