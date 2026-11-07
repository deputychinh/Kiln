import { randomUUID } from 'node:crypto';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { seedModelAsset } from './support/seed';

// A browser with WebGL switched off: the viewer must still explain itself (KILN-9 AC4).
test.use({ launchOptions: { args: ['--disable-webgl', '--disable-webgl2', '--disable-3d-apis'] } });

test('without WebGL the viewer says why and shows the still preview instead', async ({
  page,
}, testInfo) => {
  const name = `e2e_viewer_nogl_${testInfo.project.name}_${randomUUID().slice(0, 8)}`;
  const { id } = await seedModelAsset(page.request, name);
  await page.goto(`/assets/${id}`);
  await page.getByRole('link', { name: 'View version 1 in 3D' }).click({ timeout: 30_000 });

  const alert = page.getByRole('alert');
  await expect(alert).toContainText('This browser could not start 3D graphics (WebGL).');
  await expect(alert).toContainText('Showing the still preview instead.');
  await expect(page.getByRole('img', { name: 'Still preview of version 1' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Reset view' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Try again' })).toHaveCount(0);
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze();
  expect(
    results.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? '')),
  ).toEqual([]);
  await page.screenshot({
    path: `test-results/screens/viewer-fallback-${testInfo.project.name}.png`,
  });
});
