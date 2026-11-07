import { readFileSync } from 'node:fs';

import type { APIRequestContext } from '@playwright/test';

import type { components } from '@/api/kiln.schema';

import { API_URL } from './api.constant';
import { AUTH_TOKEN } from './user.constant';

const fixture = (name: string): Buffer =>
  readFileSync(new URL(`../fixtures/${name}`, import.meta.url));
const SWATCH = { fileName: 'swatch.png', mimeType: 'image/png', buffer: fixture('swatch.png') };
const CRATE = {
  fileName: 'crate.glb',
  mimeType: 'model/gltf-binary',
  buffer: fixture('crate.glb'),
};

type SeedFile = typeof SWATCH;

/** The setup project's personal access token: seeding calls the API as the CLI will. */
const asCli = (): Record<string, string> => ({
  Authorization: `Bearer ${readFileSync(AUTH_TOKEN, 'utf8').trim()}`,
});
type PendingUpload = components['schemas']['PendingUploadOut'];

const declarationOf = (file: SeedFile) => ({
  file_name: file.fileName,
  content_type: file.mimeType,
  size_bytes: file.buffer.length,
});

/** Sends the file to storage with the form the API handed out, then records the completion. */
const uploadAndComplete = async (
  request: APIRequestContext,
  pending: PendingUpload,
  file: SeedFile,
): Promise<void> => {
  if (!pending.upload) throw new Error('a new upload always has an upload form');
  const uploaded = await request.post(pending.upload.url, {
    multipart: {
      ...pending.upload.fields,
      file: { name: file.fileName, mimeType: file.mimeType, buffer: file.buffer },
    },
  });
  if (!uploaded.ok()) throw new Error(`upload failed: ${String(uploaded.status())}`);

  const completed = await request.post(
    `${API_URL}/api/v1/asset-versions/${pending.version.id}/completions`,
    { headers: asCli() },
  );
  if (!completed.ok()) throw new Error(`completion failed: ${String(completed.status())}`);
};

/** Publishes a file through the real API and storage, as the CLI will: create, upload, complete. */
const seedAsset = async (
  request: APIRequestContext,
  name: string,
  file: SeedFile,
): Promise<{ id: string; name: string }> => {
  const created = await request.post(`${API_URL}/api/v1/assets`, {
    headers: asCli(),
    data: { name, ...declarationOf(file) },
  });
  if (!created.ok()) throw new Error(`create failed: ${String(created.status())}`);
  const pending = (await created.json()) as PendingUpload;
  await uploadAndComplete(request, pending, file);
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

/** Any .glb bytes, for files the tests shape themselves. */
export const seedModelBytes = (
  request: APIRequestContext,
  name: string,
  buffer: Buffer,
): Promise<{ id: string; name: string }> =>
  seedAsset(request, name, { fileName: 'model.glb', mimeType: 'model/gltf-binary', buffer });

/** The next version of an image asset (the same small PNG). */
export const seedImageVersion = async (
  request: APIRequestContext,
  assetId: string,
): Promise<void> => {
  const created = await request.post(`${API_URL}/api/v1/assets/${assetId}/versions`, {
    headers: asCli(),
    data: declarationOf(SWATCH),
  });
  if (!created.ok()) throw new Error(`version failed: ${String(created.status())}`);
  await uploadAndComplete(request, (await created.json()) as PendingUpload, SWATCH);
};
