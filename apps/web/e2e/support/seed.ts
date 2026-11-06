import { readFileSync } from 'node:fs';

import type { APIRequestContext } from '@playwright/test';

import type { components } from '@/api/kiln.schema';

const API_URL = 'http://127.0.0.1:8000';
const SWATCH = readFileSync(new URL('../fixtures/swatch.png', import.meta.url));

/** Publishes a small PNG through the real API and storage, as the CLI will: create, upload, complete. */
export const seedImageAsset = async (
  request: APIRequestContext,
  name: string,
): Promise<{ id: string; name: string }> => {
  const created = await request.post(`${API_URL}/api/v1/assets`, {
    data: { name, file_name: 'swatch.png', content_type: 'image/png', size_bytes: SWATCH.length },
  });
  if (!created.ok()) throw new Error(`create failed: ${String(created.status())}`);
  const pending = (await created.json()) as components['schemas']['PendingUploadOut'];
  if (!pending.upload) throw new Error('a new asset always has an upload form');

  const uploaded = await request.post(pending.upload.url, {
    multipart: {
      ...pending.upload.fields,
      file: { name: 'swatch.png', mimeType: 'image/png', buffer: SWATCH },
    },
  });
  if (!uploaded.ok()) throw new Error(`upload failed: ${String(uploaded.status())}`);

  const completed = await request.post(
    `${API_URL}/api/v1/asset-versions/${pending.version.id}/completions`,
  );
  if (!completed.ok()) throw new Error(`completion failed: ${String(completed.status())}`);
  return { id: pending.asset.id, name: pending.asset.name };
};
