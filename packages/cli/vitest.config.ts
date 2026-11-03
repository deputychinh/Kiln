import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      // index.ts only wires argv to the program; the program is tested directly.
      exclude: ['src/index.ts', 'src/**/*.test.ts', 'src/**/*.enum.ts', 'src/**/*.constant.ts'],
      thresholds: { lines: 80 },
    },
  },
});
