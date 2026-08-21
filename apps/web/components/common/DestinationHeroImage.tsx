'use client'

import Image from 'next/image'
import { useWikiImage } from '@/hooks/useWikiImage'

/**
 * Client-only hero photo for a destination landing page. Split out from the
 * (server) page component because useWikiImage needs client-side fetch/state
 * — everything else on the page stays server-rendered for SEO.
 */
export function DestinationHeroImage({
  city,
  country,
  imageQuery,
  alt,
}: {
  city: string
  country: string
  imageQuery?: string
  alt: string
}) {
  const imgUrl = useWikiImage(city, country, imageQuery, 1400)

  if (!imgUrl) {
    return <div className="h-56 w-full bg-[var(--_muted)] sm:h-72" aria-hidden="true" />
  }

  return (
    <div className="relative h-56 w-full overflow-hidden sm:h-72">
      <Image
        src={imgUrl}
        alt={alt}
        fill
        // See InspirationCard.tsx — Wikimedia throttles Next's optimizer
        // fetches without a descriptive User-Agent, so serve unoptimized.
        unoptimized
        priority
        sizes="100vw"
        className="object-cover"
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent" />
    </div>
  )
}
