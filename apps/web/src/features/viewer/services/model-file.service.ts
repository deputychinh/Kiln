import { MODEL_VIEWER_MAX_BYTES } from '@/constants/viewer.constant';
import { ViewerError } from '@/enums/viewer-error.enum';
import type { ModelDownloadOptions } from '@/interfaces/viewer.interface';
import { viewerFailure } from '@/utils/viewer.util';

const lengthOf = (response: Response): number | null => {
  const length = Number(response.headers.get('Content-Length') ?? Number.NaN);
  return Number.isSafeInteger(length) && length >= 0 ? length : null;
};

const joined = (chunks: Uint8Array[], length: number): ArrayBuffer => {
  const out = new Uint8Array(length);
  let at = 0;
  for (const chunk of chunks) {
    out.set(chunk, at);
    at += chunk.length;
  }
  return out.buffer;
};

/**
 * Downloads an untrusted model file from its signed link, never more than `maxBytes`: a declared
 * or announced size over the cap fails before reading, and the stream is cut as soon as it passes
 * it. No cookies are sent and redirects are refused; a cancellation is rethrown as it is.
 */
export const downloadModel = async (
  url: string,
  { declaredBytes, maxBytes = MODEL_VIEWER_MAX_BYTES, signal, onProgress }: ModelDownloadOptions,
): Promise<ArrayBuffer> => {
  if (declaredBytes > maxBytes) throw viewerFailure(ViewerError.TooLarge);
  let response: Response;
  try {
    response = await fetch(url, {
      credentials: 'omit',
      redirect: 'error',
      mode: 'cors',
      signal: signal ?? null,
    });
  } catch (cause) {
    if (signal?.aborted) throw cause;
    throw viewerFailure(ViewerError.Download);
  }
  if (!response.ok) throw viewerFailure(ViewerError.Download);
  const announced = lengthOf(response);
  if (announced !== null && announced > maxBytes) {
    await response.body?.cancel();
    throw viewerFailure(ViewerError.TooLarge);
  }
  const total = announced ?? declaredBytes;
  onProgress?.({ loaded: 0, total });
  if (!response.body) {
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength > maxBytes) throw viewerFailure(ViewerError.TooLarge);
    onProgress?.({ loaded: buffer.byteLength, total });
    return buffer;
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let loaded = 0;
  for (;;) {
    let step: ReadableStreamReadResult<Uint8Array>;
    try {
      step = await reader.read();
    } catch (cause) {
      if (signal?.aborted) throw cause;
      throw viewerFailure(ViewerError.Download);
    }
    if (step.done) break;
    loaded += step.value.length;
    if (loaded > maxBytes) {
      await reader.cancel();
      throw viewerFailure(ViewerError.TooLarge);
    }
    chunks.push(step.value);
    onProgress?.({ loaded, total });
  }
  return joined(chunks, loaded);
};
