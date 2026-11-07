import { randomUUID } from 'node:crypto';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, type Locator, type Page, test, type TestInfo } from '@playwright/test';

import { seedModelAsset } from './support/seed';

const ORIGINS = ['http://127.0.0.1:4173', 'http://127.0.0.1:8000', 'http://127.0.0.1:8333'];
/** A change of view moves well over this share of the pixels; a reset leaves well under it. */
const CHANGED = 0.01;

const uniqueName = (testInfo: TestInfo): string =>
  `e2e_viewer_${testInfo.project.name}_${randomUUID().slice(0, 8)}`;

/** A model published through the real API, storage and worker, opened from its detail. */
const openModelInViewer = async (page: Page, testInfo: TestInfo): Promise<string> => {
  const { id, name } = await seedModelAsset(page.request, uniqueName(testInfo));
  await page.goto(`/assets/${id}`);
  // The detail polls while the worker renders the preview; the link appears once it is ready.
  // The header's action (newest ready version) comes first; the version's own link second.
  await page.getByRole('link', { name: 'View version 1 in 3D' }).first().click({ timeout: 30_000 });
  return name;
};

/**
 * Compares PNGs in the page: the share of pixels of `a` that differ from its most common colour
 * (what was drawn over the stage background), and the share that differ between `a` and `b`.
 */
const pixels = (
  page: Page,
  a: Buffer,
  b: Buffer = a,
): Promise<{ drawn: number; changed: number }> =>
  page.evaluate(
    async ([first, second]) => {
      const decode = async (base64: string): Promise<Uint8ClampedArray> => {
        const image = new Image();
        image.src = `data:image/png;base64,${base64}`;
        await image.decode();
        const canvas = document.createElement('canvas');
        canvas.width = image.width;
        canvas.height = image.height;
        const context = canvas.getContext('2d');
        if (!context) throw new Error('no 2D context');
        context.drawImage(image, 0, 0);
        return context.getImageData(0, 0, image.width, image.height).data;
      };
      const [x, y] = [await decode(first), await decode(second)];
      /** Summed RGB difference between pixel `i` of `p` and pixel `j` of `q`. */
      const distance = (p: Uint8ClampedArray, q: Uint8ClampedArray, [i, j]: [number, number]) =>
        Math.abs((p[i] ?? 0) - (q[j] ?? 0)) +
        Math.abs((p[i + 1] ?? 0) - (q[j + 1] ?? 0)) +
        Math.abs((p[i + 2] ?? 0) - (q[j + 2] ?? 0));
      const counts = new Map<string, number>();
      for (let i = 0; i < x.length; i += 4) {
        const key = `${String(x[i])},${String(x[i + 1])},${String(x[i + 2])}`;
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
      const top = [...counts.entries()].sort((m, n) => n[1] - m[1])[0]?.[0] ?? '0,0,0';
      const background = new Uint8ClampedArray(top.split(',').map(Number));
      let drawn = 0;
      let changed = 0;
      for (let i = 0; i < x.length; i += 4) {
        if (distance(x, background, [i, 0]) > 24) drawn += 1;
        if (distance(x, y, [i, i]) > 24) changed += 1;
      }
      const total = x.length / 4;
      return { drawn: drawn / total, changed: changed / total };
    },
    [a.toString('base64'), b.toString('base64')] as const,
  );

/** Only the drawing: the canvas, without the stage's focus ring. */
const canvasShot = (stage: Locator): Promise<Buffer> => stage.locator('canvas').screenshot();

const seriousViolations = async (page: Page) => {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze();
  return results.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''));
};

test('a model version opens in 3D, draws, and turns, zooms and resets with the keyboard', async ({
  page,
}, testInfo) => {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));
  const name = await openModelInViewer(page, testInfo);

  const heading = page.getByRole('heading', { level: 1, name: `Version 1 of ${name} in 3D` });
  await expect(heading).toBeFocused();
  await expect(page).toHaveURL(/\/view\?version=1$/);
  const stage = page.getByRole('application', { name: '3D view of version 1' });
  await expect(page.getByRole('button', { name: 'Reset view' })).toBeEnabled({ timeout: 20_000 });

  // WebGL (SwiftShader in headless Chromium) drew the crate over the stage background.
  const framed = await canvasShot(stage);
  expect((await pixels(page, framed)).drawn).toBeGreaterThan(0.05);
  expect(await seriousViolations(page)).toEqual([]);
  await page.screenshot({ path: `test-results/screens/viewer-${testInfo.project.name}.png` });

  // Keyboard only: Tab from the heading reaches the stage; arrows turn it, + zooms, 0 resets.
  await page.keyboard.press('Tab');
  await expect(stage).toBeFocused();
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('ArrowLeft');
  const turned = await canvasShot(stage);
  expect((await pixels(page, turned, framed)).changed).toBeGreaterThan(CHANGED);
  await page.keyboard.press('+');
  await page.keyboard.press('+');
  const zoomed = await canvasShot(stage);
  await page.screenshot({
    path: `test-results/screens/viewer-zoomed-${testInfo.project.name}.png`,
  });
  const [before, after] = [await pixels(page, turned), await pixels(page, zoomed, turned)];
  expect(after.changed).toBeGreaterThan(CHANGED);
  expect(after.drawn).toBeGreaterThan(before.drawn); // closer: the crate covers more of the view
  await page.keyboard.press('0');
  await expect
    .poll(async () => (await pixels(page, await canvasShot(stage), framed)).changed)
    .toBeLessThan(CHANGED);

  // A pointer drag orbits it (OrbitControls); Reset view brings back the framed view.
  const box = await stage.locator('canvas').boundingBox();
  if (!box) throw new Error('the canvas has no box');
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2, { steps: 8 });
  await page.mouse.up();
  await expect
    .poll(async () => (await pixels(page, await canvasShot(stage), framed)).changed)
    .toBeGreaterThan(CHANGED);
  await page.getByRole('button', { name: 'Reset view' }).click();
  await expect
    .poll(async () => (await pixels(page, await canvasShot(stage), framed)).changed)
    .toBeLessThan(CHANGED);

  // The buttons are reachable and work from the keyboard too.
  await page.getByRole('button', { name: 'Zoom out' }).focus();
  await page.keyboard.press('Enter');
  await expect
    .poll(async () => (await pixels(page, await canvasShot(stage), framed)).changed)
    .toBeGreaterThan(CHANGED);

  // Nothing but the app, the API and storage was asked for: no URI inside the file is fetched.
  const foreign = requests.filter(
    (url) => !ORIGINS.some((origin) => url.startsWith(origin)) && !/^(data|blob):/.test(url),
  );
  expect(foreign).toEqual([]);
});
