import { randomUUID } from 'node:crypto';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, type Locator, type Page, test, type TestInfo } from '@playwright/test';

import { seedImageAsset, seedModelAsset } from './support/seed';

/** Unique across parallel projects and runs (desktop and mobile seed at the same millisecond). */
const uniqueName = (prefix: string, testInfo: TestInfo): string =>
  `e2e_${prefix}_${testInfo.project.name}_${randomUUID().slice(0, 8)}`;

/** A gallery card by asset id, never by a name prefix. */
const cardOf = (page: Page, id: string): Locator => page.locator(`a[href="/assets/${id}"]`);

const seriousViolations = async (page: Page): Promise<unknown[]> => {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag22aa'])
    .analyze();
  return results.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''));
};

test('an uploaded image appears in the gallery with its preview and opens to its versions', async ({
  page,
  request,
}, testInfo) => {
  const asset = await seedImageAsset(request, uniqueName('swatch', testInfo));

  // The worker renders the preview within seconds; the gallery shows it after a reload.
  await expect(async () => {
    await page.goto('/');
    await expect(cardOf(page, asset.id).locator('img')).toBeVisible({
      timeout: 1_000,
    });
  }).toPass({ timeout: 30_000 });
  await expect(page).toHaveURL(/\/assets$/);
  expect(await seriousViolations(page)).toEqual([]);
  await page.screenshot({ path: `test-results/screens/gallery-${testInfo.project.name}.png` });

  await cardOf(page, asset.id).click();

  const detail = page.getByRole('article', { name: asset.name });
  await expect(detail.getByText('Version 1')).toBeVisible();
  await expect(detail.getByText('Ready')).toBeVisible();
  await expect(detail.getByRole('img', { name: `Preview of ${asset.name}` })).toBeVisible();
  expect(await seriousViolations(page)).toEqual([]);
  await page.screenshot({ path: `test-results/screens/detail-${testInfo.project.name}.png` });

  if (testInfo.project.name === 'mobile') {
    // Compact: the detail replaces the list, and the back link returns to it.
    await expect(page.getByRole('list', { name: 'Assets' })).toBeHidden();
    await page.getByRole('link', { name: 'All assets' }).click();
    await expect(page.getByRole('list', { name: 'Assets' })).toBeVisible();
    await expect(cardOf(page, asset.id)).toBeFocused();
  } else {
    // Expanded: list and detail side by side; the open card is marked current.
    await expect(cardOf(page, asset.id)).toHaveAttribute('aria-current', 'page');
  }
});

test('a published glTF model gets a rendered preview in the gallery and the detail', async ({
  page,
  request,
}, testInfo) => {
  const asset = await seedModelAsset(request, uniqueName('crate', testInfo));

  await expect(async () => {
    await page.goto('/assets');
    await expect(cardOf(page, asset.id).locator('img')).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 30_000 });
  await expect(cardOf(page, asset.id)).toContainText('Model');

  await cardOf(page, asset.id).click();
  const detail = page.getByRole('article', { name: asset.name });
  await expect(detail.getByText('Ready')).toBeVisible();
  const preview = detail.getByRole('img', { name: `Preview of ${asset.name}` });
  await expect(preview).toBeVisible();
  expect(await preview.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBe(512);
  await page.screenshot({ path: `test-results/screens/model-${testInfo.project.name}.png` });
});

test('the gallery can be used with the keyboard alone', async ({ page, request }, testInfo) => {
  const asset = await seedImageAsset(request, uniqueName('keys', testInfo));
  await page.goto('/assets');
  await expect(cardOf(page, asset.id)).toBeVisible();

  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  // Tab through the cards (newest first) until the seeded one has focus.
  await expect(async () => {
    await page.keyboard.press('Tab');
    await expect(cardOf(page, asset.id)).toBeFocused({ timeout: 100 });
  }).toPass({ timeout: 15_000, intervals: [0] });
  await page.keyboard.press('Enter');

  await expect(page).toHaveURL(new RegExp(`/assets/${asset.id}$`));
  await expect(page.getByRole('article', { name: asset.name })).toBeVisible();
});

test('an empty studio sees what to do first', async ({ page }) => {
  await page.route('**/api/v1/assets?*', (route) =>
    route.fulfill({ json: { items: [], next_cursor: null } }),
  );
  await page.goto('/assets');

  await expect(page.getByRole('heading', { name: 'No assets yet' })).toBeVisible();
  expect(await seriousViolations(page)).toEqual([]);
});

test('a failing API shows the problem and recovers on retry', async ({ page }) => {
  let failing = true;
  await page.route('**/api/v1/assets?*', (route) =>
    failing
      ? route.fulfill({
          status: 400,
          contentType: 'application/problem+json',
          body: JSON.stringify({
            title: 'The cursor is not valid',
            status: 400,
            code: 'INVALID_CURSOR',
          }),
        })
      : route.fulfill({ json: { items: [], next_cursor: null } }),
  );
  await page.goto('/assets');

  const alert = page.getByRole('alert');
  await expect(alert).toContainText('Could not load assets');
  await expect(alert).toContainText('The cursor is not valid');
  expect(await seriousViolations(page)).toEqual([]);

  failing = false;
  await alert.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByRole('heading', { name: 'No assets yet' })).toBeVisible();
});

test('an unknown asset link shows "not found" with a way back', async ({ page }) => {
  await page.goto('/assets/0190f1c2-0000-7000-8000-00000000dead');

  const alert = page.getByRole('alert');
  await expect(alert).toContainText('Asset not found');
  await alert.getByRole('link', { name: 'All assets' }).click();
  await expect(page).toHaveURL(/\/assets$/);
});

/** The API's preview-signing window (`DOWNLOAD_URL_WINDOW_SECONDS`). */
const WINDOW_MS = 10 * 60_000;

test('a preview seen once comes from the browser cache when the gallery opens again', async ({
  page,
  request,
}, testInfo) => {
  // Previews are signed per 10-minute window: start well clear of a window boundary (the test
  // takes seconds; the generous margin also covers a slow seed), and check it afterwards.
  const windowOf = (time: number): number => Math.floor(time / WINDOW_MS);
  const untilNextWindow = WINDOW_MS - (Date.now() % WINDOW_MS);
  if (untilNextWindow < 60_000) await page.waitForTimeout(untilNextWindow + 1_000);
  const startWindow = windowOf(Date.now());

  const asset = await seedImageAsset(request, uniqueName('cache', testInfo));
  const image = cardOf(page, asset.id).locator('img');
  const cacheHeaders = new Map<string, string | undefined>();
  page.on('response', (response) => {
    if (response.request().resourceType() === 'image')
      cacheHeaders.set(response.url(), response.headers()['cache-control']);
  });
  await expect(async () => {
    await page.goto('/assets');
    await expect(image).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 30_000 });
  const firstSrc = await image.getAttribute('src');
  // Storage told the browser it may keep the preview (privately) for the URL's lifetime.
  // Response events arrive asynchronously, possibly after the image is already on screen.
  await expect
    .poll(() => cacheHeaders.get(firstSrc ?? ''))
    .toBe('private, max-age=1500, immutable');

  // Watch the network from the browser's side: the preview is cross-origin, so resource
  // timing cannot tell a cache hit from a download, but the DevTools protocol can.
  const devtools = await page.context().newCDPSession(page);
  await devtools.send('Network.enable');
  const previewRequests = new Set<string>();
  const fromCache = new Set<string>();
  devtools.on('Network.requestWillBeSent', (event) => {
    if (event.request.url === firstSrc) previewRequests.add(event.requestId);
  });
  devtools.on('Network.requestServedFromCache', (event) => fromCache.add(event.requestId));

  // A new page load asks the API again, a few seconds later (signatures are per second): the
  // same window must give the same URL (KILN-27) …
  await page.waitForTimeout(2_000); // the passing of time is what this test is about
  await page.goto('/assets');
  await expect(image).toBeVisible();
  await expect(image).toHaveJSProperty('complete', true);
  expect(await image.getAttribute('src')).toBe(firstSrc);
  test.skip(windowOf(Date.now()) !== startWindow, 'crossed a signing window; URLs rightly changed');

  // … which the browser then serves from its cache: nothing crosses the network.
  await expect.poll(() => previewRequests.size).toBeGreaterThan(0);
  expect([...previewRequests].every((id) => fromCache.has(id))).toBe(true);
});
