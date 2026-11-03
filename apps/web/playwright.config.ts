import { defineConfig, devices } from '@playwright/test';

const WEB_URL = 'http://127.0.0.1:4173';

// Journeys run against the production build (`vite preview`) and the real API.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  reporter: 'list',
  use: { baseURL: WEB_URL, trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: [
    {
      command: 'uv run --package kiln-api uvicorn kiln_api.main:app --port 8000',
      cwd: '../..',
      url: 'http://127.0.0.1:8000/health',
      reuseExistingServer: true,
    },
    {
      command: 'npm run build && npm run preview',
      url: WEB_URL,
      reuseExistingServer: true,
    },
  ],
});
