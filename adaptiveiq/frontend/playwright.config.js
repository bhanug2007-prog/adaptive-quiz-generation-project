import { defineConfig, devices } from '@playwright/test'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'

// End-to-end test against a real backend that uses the TEST-ONLY fake model and an empty SQLite file.
const BACKEND = 8190
const WEB = 5190
const venvPython = resolve('../backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const python = process.env.PLAYWRIGHT_PYTHON || (existsSync(venvPython) ? venvPython : 'python')

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${WEB}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {},
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `"${python}" -m scripts.monitoring_test_server ${BACKEND} ${BACKEND + 1} http://localhost:${WEB}`,
      cwd: resolve('../backend'),
      env: { SEED: '0' },
      url: `http://127.0.0.1:${BACKEND}/api/health`,
      timeout: 60_000,
      reuseExistingServer: false,
    },
    {
      command: `npx vite --port ${WEB} --strictPort`,
      env: { VITE_BACKEND_URL: `http://127.0.0.1:${BACKEND}` },
      url: `http://localhost:${WEB}`,
      timeout: 60_000,
      reuseExistingServer: false,
    },
  ],
})
