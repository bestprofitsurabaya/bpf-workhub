import { defineConfig } from '@playwright/test'

// Hanya spesifikasi di e2e/ yang boleh dijalankan Playwright. Tanpa testDir,
// pola bawaan `*.test.js` ikut menangkap unit test Vitest di src/.
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // Data uji di-seed sekali per run; jalankan berurutan agar review/approve
  // tidak saling menimpa.
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5000',
    acceptDownloads: true,
    viewport: { width: 1440, height: 1000 },
    // Hanya untuk verifikasi lokal memakai Chromium sistem. CI memakai
    // browser hasil `npx playwright install chromium`.
    ...(process.env.E2E_CHROMIUM_PATH
      ? { launchOptions: { executablePath: process.env.E2E_CHROMIUM_PATH } }
      : {}),
  },
})
