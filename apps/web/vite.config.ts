import { fileURLToPath } from 'node:url';

import { tanstackRouter } from '@tanstack/router-plugin/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [tanstackRouter({ target: 'react', autoCodeSplitting: true }), react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  // The lazily loaded 3D scene (three.js) is about 1 MB; scripts/check-bundle-budget.mjs holds
  // the real budgets in gzip bytes after every build (KILN-9).
  build: { chunkSizeWarningLimit: 1100 },
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
        // Needs WebGL, which jsdom lacks: its logic is in scene/gltf services, its drawing in e2e.
        'src/features/viewer/components/ModelScene.tsx',
        'src/test/**',
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
