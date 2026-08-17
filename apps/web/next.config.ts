import type { NextConfig } from "next";
import { resolve } from "path";

const nextConfig: NextConfig = {
  // @react-pdf/renderer is ESM-only — keep it out of the SSR bundle
  serverExternalPackages: ['@react-pdf/renderer'],
  images: {
    // Remote images this app renders via `next/image`: destination photos
    // from Wikipedia's thumbnail API (hooks/useWikiImage.ts) and YouTube
    // video thumbnails.
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'upload.wikimedia.org',
        pathname: '/**',
      },
      {
        protocol: 'https',
        hostname: 'img.youtube.com',
      },
    ],
  },
  // Point Turbopack at the monorepo root so it resolves workspace-hoisted deps
  turbopack: {
    root: resolve(__dirname, '../..'),
  },
  // Proxies just the Google OAuth start/callback routes through this same
  // origin. Without this, the redirect chain is google.com → api.<domain>
  // (sets the session cookie) → <domain> — three distinct sites, with the
  // API subdomain as a pass-through "bounce". Chrome's Bounce Tracking
  // Mitigations and Safari's ITP both specifically clear cookies set on a
  // domain used only as a mid-chain bounce, so the cookie never survived to
  // the next request in *any* modern browser (confirmed via prod logs: the
  // callback succeeded server-side every time, but the immediately-following
  // /auth/me and /auth/refresh calls both came back 401). Proxying makes the
  // cookie get set by this domain directly — the one the browser actually
  // lands on — so there's no third site in the chain at all.
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
    return [
      {
        source: '/api/auth/google/:path*',
        destination: `${apiBase}/api/auth/google/:path*`,
      },
    ]
  },
};

export default nextConfig;
