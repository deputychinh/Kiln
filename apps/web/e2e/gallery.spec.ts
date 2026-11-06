import { AxeBuilder } from '@axe-core/playwright';
import { expect, type Page, test } from '@playwright/test';

import { seedImageAsset } from './support/seed';

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
  const asset = await seedImageAsset(request, `e2e_swatch_${String(Date.now())}`);

  // The worker renders the preview within seconds; the gallery shows it after a reload.
  await expect(async () => {
    await page.goto('/');
    await expect(
      page.getByRole('link', { name: new RegExp(asset.name) }).locator('img'),
    ).toBeVisible({
      timeout: 1_000,
    });
  }).toPass({ timeout: 30_000 });
  await expect(page).toHaveURL(/\/assets$/);
  expect(await seriousViolations(page)).toEqual([]);
  await page.screenshot({ path: `test-results/screens/gallery-${testInfo.project.name}.png` });

  await page.getByRole('link', { name: new RegExp(asset.name) }).click();

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
  } else {
    // Expanded: list and detail side by side; the open card is marked current.
    await expect(page.getByRole('link', { name: new RegExp(asset.name) })).toHaveAttribute(
      'aria-current',
      'page',
    );
  }
});

test('the gallery can be used with the keyboard alone', async ({ page, request }) => {
  const asset = await seedImageAsset(request, `e2e_keys_${String(Date.now())}`);
  await page.goto('/assets');
  const card = page.getByRole('link', { name: new RegExp(asset.name) });
  await expect(card).toBeVisible();

  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await card.focus();
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
