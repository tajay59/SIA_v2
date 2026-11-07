/**
 * Browser journeys (TEST_STRATEGY §3, APD §6) against the dev stack:
 *   docker compose -f deploy/compose.dev.yml up -d      (identity on :18001)
 *   npx playwright test -c tests/e2e-web
 * Builds SHOP and SIA and serves them with `vite preview` on 15173 / 15174.
 */
import { defineConfig, devices } from '@playwright/test'

export const SHOP = process.env.SHOP_URL ?? 'http://localhost:15173'
export const SIA = process.env.SIA_URL ?? 'http://localhost:15174'

export default defineConfig({
  testDir: '.',
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never', outputFolder: '../../playwright-report' }]] : 'list',
  use: {
    ...devices['Desktop Chrome'],
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  outputDir: '../../test-results',
  webServer: [
    // Production builds (what staging serves), with /api proxied to the dev identity service.
    { command: 'npm run build -w @cimh/shop && npm run preview -w @cimh/shop', url: SHOP, reuseExistingServer: !process.env.CI, timeout: 240_000, cwd: '../..' },
    { command: 'npm run build -w @cimh/sia && npm run preview -w @cimh/sia', url: SIA, reuseExistingServer: !process.env.CI, timeout: 240_000, cwd: '../..' },
  ],
})
