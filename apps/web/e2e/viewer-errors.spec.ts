import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';

import { expect, type Page, test, type TestInfo } from '@playwright/test';

import { seedModelAsset, seedModelBytes } from './support/seed';

const CRATE = readFileSync(new URL('./fixtures/crate.glb', import.meta.url));

const uniqueName = (prefix: string, testInfo: TestInfo): string =>
  `e2e_${prefix}_${testInfo.project.name}_${randomUUID().slice(0, 8)}`;

const openViewer = async (page: Page, id: string): Promise<void> => {
  await page.goto(`/assets/${id}`);
  await page.getByRole('link', { name: 'View version 1 in 3D' }).click({ timeout: 30_000 });
};

/** The crate with one more name in `extensionsUsed`: the checks pass it, three.js cannot parse it. */
const crateUsing = (extension: string): Buffer => {
  const length = CRATE.readUInt32LE(12);
  const json = JSON.parse(CRATE.subarray(20, 20 + length).toString()) as Record<string, unknown>;
  const text = Buffer.from(JSON.stringify({ ...json, extensionsUsed: [extension] }));
  const padded = Buffer.concat([text, Buffer.alloc(-text.length & 3, 0x20)]);
  const bin = CRATE.subarray(20 + length);
  const header = Buffer.alloc(20);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(20 + padded.length + bin.length, 8);
  header.writeUInt32LE(padded.length, 12);
  header.writeUInt32LE(0x4e4f534a, 16);
  return Buffer.concat([header, padded, bin]);
};

test('the viewer code failing to load offers a retry that loads it', async ({ page }, testInfo) => {
  const { id } = await seedModelAsset(page.request, uniqueName('viewer_chunk', testInfo));
  let blocked = 0;
  await page.route(/\/assets\/ModelScene-[\w-]+\.js$/, async (route) => {
    if (blocked === 0) {
      blocked += 1;
      await route.abort('connectionreset');
    } else {
      await route.continue();
    }
  });
  await openViewer(page, id);

  const alert = page.getByRole('alert');
  await expect(alert).toContainText(
    'Could not load the 3D viewer. Check your connection, then try again.',
  );
  await expect(page.getByRole('img', { name: 'Still preview of version 1' })).toBeVisible();
  await alert.getByRole('button', { name: 'Try again' }).click();

  await expect(page.getByRole('button', { name: 'Reset view' })).toBeEnabled({ timeout: 20_000 });
  expect(blocked).toBe(1);
});

test('losing the WebGL context while a model is shown falls back to the still preview', async ({
  page,
}, testInfo) => {
  const { id } = await seedModelAsset(page.request, uniqueName('viewer_lost', testInfo));
  await openViewer(page, id);
  await expect(page.getByRole('button', { name: 'Reset view' })).toBeEnabled({ timeout: 20_000 });

  await page
    .getByRole('application', { name: '3D view of version 1' })
    .locator('canvas')
    .evaluate((canvas: HTMLCanvasElement) => {
      const context = canvas.getContext('webgl2') ?? canvas.getContext('webgl');
      context?.getExtension('WEBGL_lose_context')?.loseContext();
    });

  await expect(page.getByRole('alert')).toContainText(
    'This browser could not start 3D graphics (WebGL).',
  );
  await expect(page.getByRole('img', { name: 'Still preview of version 1' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Reset view' })).toBeDisabled();
});

test('a file three.js cannot parse after the checks is called unreadable, not a failed download', async ({
  page,
}, testInfo) => {
  const file = crateUsing('KHR_draco_mesh_compression'); // used, not required: the worker draws it
  const { id } = await seedModelBytes(page.request, uniqueName('viewer_parse', testInfo), file);
  await openViewer(page, id);

  const alert = page.getByRole('alert');
  await expect(alert).toContainText('This file is not a glTF binary (.glb) the viewer can read.');
  await expect(alert.getByRole('button', { name: 'Try again' })).toHaveCount(0);
  await expect(page.getByRole('img', { name: 'Still preview of version 1' })).toBeVisible();
});
