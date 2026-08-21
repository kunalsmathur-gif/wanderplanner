import type { MetadataRoute } from 'next'

const SITE_URL = 'https://wanderplanner.org'

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: SITE_URL,
      lastModified: new Date(),
      changeFrequency: 'weekly',
      priority: 1,
    },
    {
      url: `${SITE_URL}/privacy`,
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: `${SITE_URL}/terms`,
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    // `/t/[slug]` shared-trip pages are intentionally excluded — they're
    // marked noindex (view-only, ephemeral, no canonical SEO value).
  ]
}
