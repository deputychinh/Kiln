import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, type Page, test, type TestInfo } from '@playwright/test';

const SWATCH = readFileSync(new URL('./fixtures/swatch.png', import.meta.url));

const uniqueName = (prefix: string, testInfo: TestInfo): string =>
  `e2e_${prefix}_${testInfo.project.name}_${randomUUID().slice(0, 8)}`;

/** An asset with two ready versions, made through the UI against the real API, storage and worker. */
const assetWithTwoVersions = async (page: Page, testInfo: TestInfo): Promise<string> => {
  const name = uniqueName('compare', testInfo);
  await page.goto('/assets');
  await page
    .getByRole('group', { name: 'Drop images or .glb files here' })
    .locator('input[type="file"]')
    .setInputFiles({ name: `${name}.png`, mimeType: 'image/png', buffer: SWATCH });
  const row = page
    .getByRole('list', { name: 'Uploads' })
    .getByRole('listitem')
    .filter({ hasText: `${name}.png` });
  await expect(row.getByText('Ready')).toBeVisible({ timeout: 30_000 });
  await row.getByRole('link').click();

  const detail = page.getByRole('article', { name });
  await detail
    .getByRole('group', { name: `Drop a new version of ${name} here` })
    .locator('input[type="file"]')
    .setInputFiles({ name: `${name}_v2.png`, mimeType: 'image/png', buffer: SWATCH });
  await expect(
    detail
      .getByRole('list', { name: `New versions of ${name}` })
      .getByRole('listitem')
      .getByText('Ready'),
  ).toBeVisible({ timeout: 30_000 });
  return name;
};

test('two versions compared side by side and by swipe, with the pair kept in the URL', async ({
  page,
}, testInfo) => {
  const name = await assetWithTwoVersions(page, testInfo);
  await page.getByRole('link', { name: 'Compare versions' }).click();

  const heading = page.getByRole('heading', { level: 1, name: `Compare versions of ${name}` });
  await expect(heading).toBeFocused();
  await expect(page.getByRole('figure', { name: 'Version 1' }).getByRole('img')).toBeVisible();
  await expect(page.getByRole('figure', { name: 'Version 2' }).getByRole('img')).toBeVisible();
  await expect(page.getByText('Versions 2 and 1 are the same size.')).toBeVisible();
  let results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag22aa'])
    .analyze();
  expect(
    results.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? '')),
  ).toEqual([]);
  await page.screenshot({ path: `test-results/screens/compare-side-${testInfo.project.name}.png` });

  // Keyboard only: choose Swipe, then move the slider with the arrow keys.
  await page.getByRole('radio', { name: 'Swipe' }).check();
  await expect(page).toHaveURL(/mode=swipe/);
  const slider = page.getByRole('slider', { name: 'Divider between version 1 and version 2' });
  await slider.focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  await expect(slider).toHaveValue('52');
  // Left of the divider is the left picker's version: the right one is clipped from the left edge.
  await expect(page.getByRole('img', { name: 'Preview of version 2' })).toHaveCSS(
    'clip-path',
    'inset(0px 0px 0px 52%)',
  );
  results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag22aa']).analyze();
  expect(
    results.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? '')),
  ).toEqual([]);
  await page.screenshot({
    path: `test-results/screens/compare-swipe-${testInfo.project.name}.png`,
  });

  // The URL is the state: a reload shows the same comparison.
  await page.reload();
  await expect(
    page.getByRole('slider', { name: 'Divider between version 1 and version 2' }),
  ).toBeVisible();
});
