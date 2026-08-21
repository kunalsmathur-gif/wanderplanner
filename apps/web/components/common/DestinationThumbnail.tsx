'use client'

import Image from 'next/image'
import { useWikiImage } from '@/hooks/useWikiImage'
import type { Destination } from '@/lib/destinationsData'

/**
 * Photo thumbnail for the /destinations hub grid — same visual language as
 * the homepage's InspirationCard, but a real <Link> to the SEO guide page
 * instead of an onClick that opens the wizard directly. Split into its own
 * client component because useWikiImage needs client-side fetch/state; the
 * parent index page stays a server component for its own content/metadata.
 */
export function DestinationThumbnail({ dest }: { dest: Destination }) {
  const imgUrl = useWikiImage(dest.city, dest.country, dest.imageQuery)

  return (
    <div className="relative h-32 w-full overflow-hidden rounded-t-2xl bg-[var(--_muted)]">
      {imgUrl && (
        <Image
          src={imgUrl}
          alt={dest.label}
          fill
          unoptimized
          sizes="(min-width: 1024px) 25vw, (min-width: 640px) 33vw, 50vw"
          className="object-cover transition-transform duration-500 group-hover:scale-105"
          loading="lazy"
        />
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/10 to-transparent" />
      <span className="absolute right-3 top-3 text-xl drop-shadow">{dest.emoji}</span>
    </div>
  )
}
