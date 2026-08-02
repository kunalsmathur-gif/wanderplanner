import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    // 🔴 `true`, not the usual `!process.env.CI`. CI deliberately runs E2E
    // against a **production** build — it does `npm run build` then
    // `npm run start` before this, because `next dev` does not prerender and
    // therefore misses a whole class of bug (v10.55.0 shipped a page that
    // dereferenced a client-only API during prerender with every other check
    // green). With the default, Playwright refuses to reuse that server and
    // tries to start `npm run dev` on the same port, failing the run with
    // "http://localhost:3000 is already used" before a single test executes.
    // Locally nothing is usually listening, so this still starts a dev server
    // on demand — and reuses one you already have running, which is what you
    // want anyway.
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
