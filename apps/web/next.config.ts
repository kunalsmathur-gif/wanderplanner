import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // @react-pdf/renderer is ESM-only — keep it out of the SSR bundle
  serverExternalPackages: ['@react-pdf/renderer'],
  // Silence monorepo root detection warning
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
