import { readFileSync } from 'node:fs';

import type { APIRequestContext } from '@playwright/test';

import type { components } from '@/api/kiln.schema';

const API_URL = 'http://127.0.0.1:8000';
const fixture = (name: string): Buffer =>
  readFileSync(new URL(`../fixtures/${name}`, import.meta.url));
const SWATCH = { fileName: 'swatch.png', mimeType: 'image/png', buffer: fixture('swatch.png') };
const CRATE = {
  fileName: 'crate.glb',
  mimeType: 'model/gltf-binary',
  buffer: fixture('crate.glb'),
};

type SeedFile = typeof SWATCH;

/** Publishes a file through the real API and storage, as the CLI will: create, upload, complete. */
const seedAsset = async (
  request: APIRequestContext,
  name: string,
  file: SeedFile,
): Promise<{ id: string; name: string }> => {
  const created = await request.post(`${API_URL}/api/v1/assets`, {
    data: {
      name,
      file_name: file.fileName,
      content_type: file.mimeType,
      size_bytes: file.buffer.length,
    },
  });
  if (!created.ok()) throw new Error(`create failed: ${String(created.status())}`);
  const pending = (await created.json()) as components['schemas']['PendingUploadOut'];
  if (!pending.upload) throw new Error('a new asset always has an upload form');

  const uploaded = await request.post(pending.upload.url, {
    multipart: {
      ...pending.upload.fields,
      file: { name: file.fileName, mimeType: file.mimeType, buffer: file.buffer },
    },
  });
  if (!uploaded.ok()) throw new Error(`upload failed: ${String(uploaded.status())}`);

  const completed = await request.post(
    `${API_URL}/api/v1/asset-versions/${pending.version.id}/completions`,
  );
  if (!completed.ok()) throw new Error(`completion failed: ${String(completed.status())}`);
  return { id: pending.asset.id, name: pending.asset.name };
};

/** A small PNG. */
export const seedImageAsset = (
  request: APIRequestContext,
  name: string,
): Promise<{ id: string; name: string }> => seedAsset(request, name, SWATCH);

/** A small glTF binary (a cube). */
export const seedModelAsset = (
  request: APIRequestContext,
  name: string,
): Promise<{ id: string; name: string }> => seedAsset(request, name, CRATE);
