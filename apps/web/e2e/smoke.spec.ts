import { AxeBuilder } from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('the home page shows the brand and reports that the API is online', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('banner')).toContainText('Kiln');
  await expect(page.getByRole('status')).toContainText('API online');
});

test('the home page has no serious accessibility violations', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('status')).toContainText('API online');

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag22aa'])
    .analyze();
  const serious = results.violations.filter((v) =>
    ['serious', 'critical'].includes(v.impact ?? ''),
  );

  expect(serious).toEqual([]);
});
