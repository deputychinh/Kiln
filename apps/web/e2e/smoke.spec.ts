import { expect, test } from '@playwright/test';

test('the app opens on the gallery behind the brand header', async ({ page }) => {
  await page.goto('/');

  await expect(page).toHaveURL(/\/assets$/);
  await expect(page.getByRole('banner')).toContainText('Kiln');
  await expect(page.getByRole('heading', { level: 1, name: 'Assets' })).toBeVisible();
});
