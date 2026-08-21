import type { MetadataRoute } from 'next'

const SITE_URL = 'https://wanderplanner.org'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        // Auth-gated / private app surfaces — no SEO value, keep crawl budget on marketing pages
        disallow: ['/account', '/admin', '/dev', '/api/', '/login', '/signup', '/forgot-password', '/reset-password'],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
  }
}
