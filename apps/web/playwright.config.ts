import { defineConfig, devices } from '@playwright/test';

import { AUTH_STATE } from './e2e/support/user.constant';

const WEB_URL = 'http://127.0.0.1:4173';

// Journeys run against the production build (`vite preview`), the real API and the worker
// (needs `make up` and `make migrate`).
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  reporter: 'list',
  use: { baseURL: WEB_URL, trace: 'retain-on-failure' },
  // Every journey runs signed in: the setup project signs in once through the UI (KILN-12).
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/u },
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], storageState: AUTH_STATE },
      dependencies: ['setup'],
    },
    {
      name: 'mobile',
      use: { ...devices['Pixel 7'], storageState: AUTH_STATE },
      dependencies: ['setup'],
    },
  ],
  webServer: [
    {
      command: 'uv run --package kiln-api python -m kiln_api.serve --port 8000',
      cwd: '../..',
      url: 'http://127.0.0.1:8000/health',
      reuseExistingServer: true,
    },
    {
      // Renders the previews the gallery journey waits for; logs "worker started" when polling.
      command: 'uv run --package kiln-worker python -m kiln_worker',
      cwd: '../..',
      wait: { stderr: /worker started/ },
      gracefulShutdown: { signal: 'SIGTERM', timeout: 10_000 },
    },
    {
      command: 'npm run build && npm run preview',
      url: WEB_URL,
      reuseExistingServer: true,
    },
  ],
});
