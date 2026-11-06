import { defineConfig, devices } from '@playwright/test';

const STORYBOOK_URL = 'http://127.0.0.1:6007';

// Every story of the static Storybook build, in both themes, through axe (KILN-7).
export default defineConfig({
  testDir: './e2e',
  reporter: 'list',
  use: { baseURL: STORYBOOK_URL, trace: 'retain-on-failure' },
  projects: [{ name: 'desktop', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    // CI has just built Storybook in the build step; locally the build is always fresh.
    command: `${process.env.CI ? '' : 'npm run build && '}vite preview --outDir storybook-static --host 127.0.0.1 --port 6007 --strictPort`,
    url: STORYBOOK_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
