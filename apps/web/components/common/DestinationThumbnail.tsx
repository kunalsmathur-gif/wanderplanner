import Image from 'next/image'
import type { Destination } from '@/lib/destinationsData'

/**
 * Photo thumbnail for the /destinations hub grid — same visual language as
 * the homepage's InspirationCard. Reuses the same curated Pexels heroImage
 * as the guide page's hero banner (see lib/destinationsData.ts) instead of
 * a live Wikipedia thumbnail fetch, so this is a plain server component now
 * (no client fetch/flash, one fewer client-JS chunk).
 */
export function DestinationThumbnail({ dest }: { dest: Destination }) {
  return (
    <div className="relative h-32 w-full overflow-hidden rounded-t-2xl bg-[var(--_muted)]">
      <Image
        src={dest.heroImage.url}
        alt={dest.label}
        fill
        sizes="(min-width: 1024px) 25vw, (min-width: 640px) 33vw, 50vw"
        className="object-cover object-[50%_35%] transition-transform duration-500 group-hover:scale-105"
        loading="lazy"
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/10 to-transparent" />
      <span className="absolute right-3 top-3 text-xl drop-shadow">{dest.emoji}</span>
    </div>
  )
}
