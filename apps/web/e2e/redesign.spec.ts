import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, type Locator, type Page, test, type TestInfo } from '@playwright/test';

import { seedImageAsset, seedImageVersion, seedModelAsset } from './support/seed';

const SWATCH = readFileSync(new URL('./fixtures/swatch.png', import.meta.url));

const uniqueName = (prefix: string, testInfo: TestInfo): string =>
  `e2e_${prefix}_${testInfo.project.name}_${randomUUID().slice(0, 8)}`;

const cardOf = (page: Page, id: string): Locator =>
  page.locator(`a[href^="/assets/${id}"]`).first();

const seriousViolations = async (page: Page): Promise<string[]> => {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze();
  return results.violations
    .filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))
    .map((v) => `${v.id}: ${v.nodes.map((node) => node.target.join(' ')).join(', ')}`);
};

/** Waits until the worker has made the asset's preview (the gallery reloads until it shows). */
const waitForPreview = async (page: Page, id: string): Promise<void> => {
  await expect(async () => {
    await page.goto('/assets');
    await expect(cardOf(page, id).locator('img')).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 45_000 });
};

const BACKGROUND = { dark: 'rgb(19, 19, 22)', light: 'rgb(250, 250, 250)' } as const;

for (const theme of ['dark', 'light'] as const) {
  test.describe(`${theme} theme`, () => {
    // No transitions: axe measures contrast at one instant, and a pill fading out of a card the
    // pointer just left is not a resting state.
    test.use({ colorScheme: theme, reducedMotion: 'reduce' });

    test(`gallery, detail, compare and the 3D viewer pass axe in the ${theme} theme`, async ({
      page,
      request,
    }, testInfo) => {
      test.setTimeout(120_000);
      const image = await seedImageAsset(request, uniqueName(`axe_${theme}`, testInfo));
      await seedImageVersion(request, image.id);
      const model = await seedModelAsset(request, uniqueName(`axe3d_${theme}`, testInfo));
      await waitForPreview(page, image.id);
      await waitForPreview(page, model.id);

      // The tokens follow the system theme until the person chooses one.
      await expect(page.locator('body')).toHaveCSS('background-color', BACKGROUND[theme]);
      expect(await seriousViolations(page), 'gallery').toEqual([]);
      // Reflow (1.4.10): nothing, not even a hidden tooltip, widens the page past the window.
      const width = page.viewportSize()?.width ?? 0;
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width,
      );

      await cardOf(page, image.id).click();
      const detail = page.getByRole('article', { name: image.name });
      await expect(detail.getByRole('tab', { name: 'Versions 2' })).toBeVisible();
      await expect(detail.locator('.asset-detail__versions > li')).toHaveCount(2);
      await expect(detail.locator('.asset-detail__versions > li').first()).toContainText('Ready', {
        timeout: 30_000,
      });
      expect(await seriousViolations(page), 'detail').toEqual([]);
      await detail.getByRole('tab', { name: 'Info' }).click();
      expect(await seriousViolations(page), 'detail info').toEqual([]);

      await page.goto(`/assets/${image.id}/compare`);
      await expect(page.getByRole('figure', { name: 'Version 2' }).getByRole('img')).toBeVisible();
      expect(await seriousViolations(page), 'compare').toEqual([]);

      await page.goto(`/assets/${model.id}/view`);
      await expect(page.getByRole('button', { name: 'Reset view' })).toBeEnabled({
        timeout: 20_000,
      });
      expect(await seriousViolations(page), 'viewer').toEqual([]);
    });
  });
}

test.describe('theme switch', () => {
  test.use({ colorScheme: 'dark' });

  test('switches to light over a dark system theme and keeps the choice after a reload', async ({
    page,
  }) => {
    await page.goto('/assets');
    await expect(page.locator('body')).toHaveCSS('background-color', BACKGROUND.dark);

    await page.getByRole('button', { name: 'Switch to light theme' }).click();

    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await expect(page.locator('body')).toHaveCSS('background-color', BACKGROUND.light);
    await page.reload();
    await expect(page.getByRole('button', { name: 'Switch to dark theme' })).toBeVisible();
    await expect(page.locator('body')).toHaveCSS('background-color', BACKGROUND.light);
  });
});

test('the kind filter and the card size live in the URL and survive a reload', async ({
  page,
  request,
}, testInfo) => {
  const image = await seedImageAsset(request, uniqueName('filter_img', testInfo));
  const model = await seedModelAsset(request, uniqueName('filter_glb', testInfo));
  await page.goto('/assets');
  await expect(cardOf(page, model.id)).toBeVisible();
  await expect(cardOf(page, image.id)).toBeVisible();

  const options = page.getByRole('group', { name: 'Gallery options' });
  await options.getByRole('radio', { name: 'Models' }).check();
  await expect(page).toHaveURL(/\?kind=model$/);
  await expect(cardOf(page, model.id)).toBeVisible();
  await expect(cardOf(page, image.id)).toHaveCount(0);

  await options.getByRole('radio', { name: 'Small cards' }).check();
  await expect(page).toHaveURL(/kind=model&size=small|size=small&kind=model/);
  await page.reload();
  await expect(page.getByRole('radio', { name: 'Models' })).toBeChecked();
  await expect(page.getByRole('radio', { name: 'Small cards' })).toBeChecked();
  await expect(cardOf(page, image.id)).toHaveCount(0);

  // The open asset keeps the view: back to the gallery returns to the same filter.
  await cardOf(page, model.id).click();
  await expect(page).toHaveURL(new RegExp(`/assets/${model.id}\\?`));
  expect(await seriousViolations(page)).toEqual([]);
});

test('files dropped on the open asset become its next version, outside the upload tray', async ({
  page,
  request,
}, testInfo) => {
  const asset = await seedImageAsset(request, uniqueName('dropversion', testInfo));
  const fileName = `${uniqueName('dropped', testInfo)}.png`;
  await page.goto(`/assets/${asset.id}`);
  const detail = page.getByRole('article', { name: asset.name });
  await expect(detail).toBeVisible();

  const dataTransfer = await page.evaluateHandle(
    ({ name, base64 }) => {
      const transfer = new DataTransfer();
      const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
      transfer.items.add(new File([bytes], name, { type: 'image/png' }));
      return transfer;
    },
    { name: fileName, base64: SWATCH.toString('base64') },
  );
  await page.locator('main').dispatchEvent('dragenter', { dataTransfer });
  const target = page.locator('[data-drop-target="version"]');
  await expect(target).toContainText(`New version of ${asset.name}`);
  await expect(page.locator('.drop-overlay')).toHaveCSS('opacity', '1'); // its fade-in is done
  await page.screenshot({ path: `test-results/screens/drop-overlay-${testInfo.project.name}.png` });
  await target.dispatchEvent('drop', { dataTransfer });

  const row = detail
    .getByRole('list', { name: `New versions of ${asset.name}` })
    .getByRole('listitem')
    .filter({ hasText: fileName });
  await expect(row.getByText('Ready')).toBeVisible({ timeout: 30_000 });
  await expect(detail.getByRole('tab', { name: 'Versions 2' })).toBeVisible();
  // Versions belong to their asset's list, not to the tray of new assets.
  await expect(page.getByRole('region', { name: 'Uploads' })).toBeHidden();
});

test.describe('card size', () => {
  // Desktop only: the widths are set here, and the mobile project emulates a touch phone.
  test.skip(({ isMobile }) => isMobile, 'viewport widths are set explicitly');

  for (const width of [390, 768, 1024, 1440]) {
    test(`small cards are narrower than large ones at ${String(width)} px`, async ({
      page,
      request,
    }, testInfo) => {
      await seedImageAsset(request, uniqueName(`size${String(width)}`, testInfo));
      await page.setViewportSize({ width, height: 900 });
      const cardWidth = async (path: string): Promise<number> => {
        await page.goto(path);
        const card = page.getByRole('list', { name: 'Assets' }).locator('.asset-card').first();
        await expect(card).toBeVisible();
        return (await card.boundingBox())?.width ?? 0;
      };

      const large = await cardWidth('/assets');
      const small = await cardWidth('/assets?size=small');

      // A different column count, not a few pixels: the control always changes the layout.
      expect(small).toBeLessThan(large * 0.85);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width,
      );
    });
  }
});
