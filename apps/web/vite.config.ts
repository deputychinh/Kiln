import { fileURLToPath } from 'node:url';

import { tanstackRouter } from '@tanstack/router-plugin/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [tanstackRouter({ target: 'react', autoCodeSplitting: true }), react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    env: { VITE_KILN_API_URL: 'http://api.test' },
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      // Routes and the entry point are covered by the build and Playwright.
      exclude: [
        'src/main.tsx',
        'src/routes/**',
        'src/routeTree.gen.ts',
        'src/api/**',
        'src/**/index.ts',
        'src/**/*.test.{ts,tsx}',
        'src/**/*.constant.ts',
        'src/**/*.enum.ts',
        'src/**/*.interface.ts',
      ],
      thresholds: { lines: 80 },
    },
  },
});
