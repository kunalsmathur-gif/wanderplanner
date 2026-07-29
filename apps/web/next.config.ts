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
};

export default nextConfig;
