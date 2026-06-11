import type { NextConfig } from "next";
import { resolve } from "path";

const nextConfig: NextConfig = {
  // @react-pdf/renderer is ESM-only — keep it out of the SSR bundle
  serverExternalPackages: ['@react-pdf/renderer'],
  // Point Turbopack at the monorepo root so it resolves workspace-hoisted deps
  turbopack: {
    root: resolve(__dirname, '../..'),
  },
};

export default nextConfig;
