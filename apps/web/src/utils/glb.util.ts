import {
  GLB_MAX_JSON_BYTES,
  VIEWER_MATERIAL_EXTENSION_PREFIX,
  VIEWER_REQUIRED_EXTENSIONS,
} from '@/constants/viewer.constant';
import { ViewerError } from '@/enums/viewer-error.enum';

const GLB_MAGIC = 0x46546c67; // "glTF"
const GLB_VERSION = 2;
const JSON_CHUNK = 0x4e4f534a;
const HEADER_BYTES = 12;
const CHUNK_HEADER_BYTES = 8;
const EMBEDDED_URL = /^(?:blob|data):/i;

/** Only URLs inside the file itself: GLTFLoader's `blob:` image URLs and `data:` URIs. */
export const isEmbeddedUrl = (url: string): boolean => EMBEDDED_URL.test(url);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

/** The entries of an optional top-level list; null when it is there but not a list. */
const listOf = (json: Record<string, unknown>, key: string): unknown[] | null => {
  const value = json[key];
  if (value === undefined) return [];
  return Array.isArray(value) ? value : null;
};

const isSupportedExtension = (name: unknown): boolean =>
  typeof name === 'string' &&
  (VIEWER_REQUIRED_EXTENSIONS.has(name) || name.startsWith(VIEWER_MATERIAL_EXTENSION_PREFIX));

const readJson = (buffer: ArrayBuffer): Record<string, unknown> | ViewerError => {
  const view = new DataView(buffer);
  const jsonLength = view.getUint32(HEADER_BYTES, true);
  if (view.getUint32(HEADER_BYTES + 4, true) !== JSON_CHUNK) return ViewerError.Unreadable;
  if (jsonLength > GLB_MAX_JSON_BYTES) return ViewerError.TooLarge;
  const start = HEADER_BYTES + CHUNK_HEADER_BYTES;
  if (start + jsonLength > buffer.byteLength) return ViewerError.Unreadable;
  try {
    const text = new TextDecoder('utf-8', { fatal: true }).decode(
      new Uint8Array(buffer, start, jsonLength),
    );
    const json: unknown = JSON.parse(text);
    return isRecord(json) ? json : ViewerError.Unreadable;
  } catch {
    return ViewerError.Unreadable;
  }
};

/**
 * Checks an untrusted .glb before it is parsed (glTF 2.0 §4.4): a GLB 2 header whose length is the
 * file's, a JSON chunk first and no larger than the worker reads, no buffer that names a file, no
 * image outside the file, and no required extension that needs a decoder from elsewhere.
 * Returns why it cannot be shown, or null.
 */
export const inspectGlb = (buffer: ArrayBuffer): ViewerError | null => {
  if (buffer.byteLength < HEADER_BYTES + CHUNK_HEADER_BYTES) return ViewerError.Unreadable;
  const view = new DataView(buffer);
  if (
    view.getUint32(0, true) !== GLB_MAGIC ||
    view.getUint32(4, true) !== GLB_VERSION ||
    view.getUint32(8, true) !== buffer.byteLength
  ) {
    return ViewerError.Unreadable;
  }
  const json = readJson(buffer);
  if (!isRecord(json)) return json;

  const buffers = listOf(json, 'buffers');
  const images = listOf(json, 'images');
  const required = listOf(json, 'extensionsRequired');
  if (buffers === null || images === null || required === null) return ViewerError.Unreadable;
  // Every buffer is the BIN chunk: a `uri`, even a data URI, is something the worker refuses too.
  if (buffers.some((entry) => isRecord(entry) && entry.uri !== undefined)) {
    return ViewerError.ExternalReference;
  }
  const isOutside = (entry: unknown): boolean =>
    isRecord(entry) &&
    entry.uri !== undefined &&
    (typeof entry.uri !== 'string' || !entry.uri.startsWith('data:'));
  if (images.some(isOutside)) return ViewerError.ExternalReference;
  if (!required.every(isSupportedExtension)) return ViewerError.Unsupported;
  return null;
};
