import Image from 'next/image'
import type { DestinationHeroImage as HeroImage } from '@/lib/destinationsData'

/**
 * Hero photo for a destination landing page. Renders a curated, one-time
 * Pexels photo (see lib/destinationsData.ts) instead of a live Wikipedia
 * thumbnail — that fetch was returning low-res/oddly-cropped images once
 * stretched across this full-width banner. Pure server component now (no
 * client fetch/state needed), which also drops one client-JS chunk.
 */
export function DestinationHeroImage({
  heroImage,
  alt,
}: {
  heroImage: HeroImage
  alt: string
}) {
  return (
    <div className="relative h-56 w-full overflow-hidden sm:h-72">
      <Image
        src={heroImage.url}
        alt={alt}
        fill
        priority
        sizes="100vw"
        // `object-position: 50% 35%` biases the crop slightly above center —
        // landscape/skyline/temple shots tend to have their most interesting
        // detail (skyline, temple roofline, mountain peak) in the upper half,
        // and a plain center crop was clipping it on short (h-56) mobile crops.
        className="object-cover object-[50%_35%]"
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent" />
      {/* Pexels license requires visible photographer attribution */}
      <a
        href={heroImage.photographerUrl}
        target="_blank"
        rel="noopener noreferrer nofollow"
        className="absolute bottom-2 right-2 rounded bg-black/40 px-2 py-0.5 text-[10px] text-white/80 backdrop-blur-sm hover:text-white"
      >
        Photo: {heroImage.photographer} / Pexels
      </a>
    </div>
  )
}
