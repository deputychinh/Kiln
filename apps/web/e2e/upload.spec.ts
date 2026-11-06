import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, type Locator, type Page, test, type TestInfo } from '@playwright/test';

const SWATCH = readFileSync(new URL('./fixtures/swatch.png', import.meta.url));
const CRATE = readFileSync(new URL('./fixtures/crate.glb', import.meta.url));

/** Unique across parallel projects and runs, so each upload is its own asset. */
const uniqueFileName = (prefix: string, extension: string, testInfo: TestInfo): string =>
  `e2e_${prefix}_${testInfo.project.name}_${randomUUID().slice(0, 8)}.${extension}`;

const dropzone = (page: Page): Locator =>
  page.getByRole('group', { name: 'Drop images or .glb files here' });

const uploadRow = (page: Page, fileName: string): Locator =>
  page.getByRole('list', { name: 'Uploads' }).getByRole('listitem').filter({ hasText: fileName });

/** The new asset's id, from the link a ready row offers. */
const assetIdOf = async (row: Locator): Promise<string> => {
  const href = await row.getByRole('link').getAttribute('href');
  return href?.split('/').pop() ?? '';
};

test('an image chosen with the file button uploads and its preview appears in the gallery', async ({
  page,
}, testInfo) => {
  const fileName = uniqueFileName('upload', 'png', testInfo);
  await page.goto('/assets');

  await dropzone(page)
    .locator('input[type="file"]')
    .setInputFiles([
      { name: fileName, mimeType: 'image/png', buffer: SWATCH },
      { name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('not an image') },
    ]);

  const refused = uploadRow(page, 'notes.txt');
  await expect(refused).toContainText('Only PNG, JPEG, WebP and .glb files can be uploaded.');
  await expect(refused.getByRole('button', { name: 'Remove notes.txt' })).toBeVisible();

  const row = uploadRow(page, fileName);
  await expect(row.getByText('Ready')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('1 of 2 uploaded')).toBeVisible();

  // No reload: the gallery refreshed itself and shows the rendered preview.
  const assetId = await assetIdOf(row);
  await expect(page.locator(`a[href="/assets/${assetId}"] img`)).toBeVisible();

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag22aa'])
    .analyze();
  expect(
    results.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? '')),
  ).toEqual([]);
  await page.screenshot({ path: `test-results/screens/upload-${testInfo.project.name}.png` });

  await refused.getByRole('button', { name: 'Remove notes.txt' }).click();
  await expect(refused).toHaveCount(0);
});

test('a glTF model dropped on the dropzone uploads and gets a rendered preview', async ({
  page,
}, testInfo) => {
  const fileName = uniqueFileName('drop', 'glb', testInfo);
  await page.goto('/assets');
  await expect(dropzone(page)).toBeVisible();

  const dataTransfer = await page.evaluateHandle(
    ({ name, base64 }) => {
      const transfer = new DataTransfer();
      const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
      transfer.items.add(new File([bytes], name)); // browsers report .glb with no type
      return transfer;
    },
    { name: fileName, base64: CRATE.toString('base64') },
  );
  await dropzone(page).dispatchEvent('dragenter', { dataTransfer });
  await expect(dropzone(page)).toHaveClass(/dropzone--active/);
  await dropzone(page).dispatchEvent('drop', { dataTransfer });

  const row = uploadRow(page, fileName);
  await expect(row.getByText('Ready')).toBeVisible({ timeout: 60_000 });
  const assetId = await assetIdOf(row);
  await expect(page.locator(`a[href="/assets/${assetId}"] img`)).toBeVisible();
});

test('a slow upload can be cancelled from the keyboard, retried with the same key, and recovers from a storage refusal', async ({
  page,
}, testInfo) => {
  const fileName = uniqueFileName('slow', 'png', testInfo);
  const keys: string[] = [];
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/v1/assets'))
      keys.push(request.headers()['idempotency-key'] ?? '');
  });
  // Storage: the first transfer hangs (a slow network), the second is refused, the third goes through.
  let transfers = 0;
  await page.route(
    (url) => url.port === '8333',
    async (route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      transfers += 1;
      if (transfers === 1) return new Promise<void>(() => undefined);
      if (transfers === 2)
        return route.fulfill({
          status: 403,
          body: '<Error><Code>AccessDenied</Code></Error>',
          headers: { 'Access-Control-Allow-Origin': new URL(page.url()).origin },
        });
      return route.fallback();
    },
  );
  await page.goto('/assets');
  await dropzone(page)
    .locator('input[type="file"]')
    .setInputFiles({ name: fileName, mimeType: 'image/png', buffer: SWATCH });

  const row = uploadRow(page, fileName);
  await expect(row.getByText(/^Uploading/)).toBeVisible();
  await expect(row.getByRole('progressbar', { name: `Uploading ${fileName}` })).toBeVisible();
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag22aa'])
    .analyze();
  expect(
    results.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? '')),
  ).toEqual([]);
  await page.screenshot({
    path: `test-results/screens/upload-running-${testInfo.project.name}.png`,
  });

  // Keyboard only: Cancel, then Retry where focus lands.
  // Real Tab order: from Choose files, the next stop is this row's Cancel.
  await page.getByRole('button', { name: 'Choose files' }).focus();
  await page.keyboard.press('Tab');
  await expect(row.getByRole('button', { name: `Cancel ${fileName}` })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(row.getByText('Cancelled', { exact: true })).toBeVisible();
  const retry = row.getByRole('button', { name: `Retry ${fileName}` });
  await expect(retry).toBeFocused();
  await page.keyboard.press('Enter');

  await expect(row).toContainText('Storage refused the file. Try again.');
  await retry.click();
  await expect(row.getByText('Ready')).toBeVisible({ timeout: 30_000 });

  // Three attempts, one asset: every create carried the same idempotency key.
  expect(keys).toHaveLength(3);
  expect(new Set(keys).size).toBe(1);
  await page.unrouteAll({ behavior: 'ignoreErrors' });
});
