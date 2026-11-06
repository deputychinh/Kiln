import { apiError, apiPost } from '@/api/client';
import { ASSETS_PATH } from '@/constants/assets.constant';
import {
  completionsPath,
  STORAGE_REJECTED_CODE,
  UPLOAD_API_TIMEOUT_MS,
  UPLOAD_STALL_MS,
  UPLOAD_STALLED_CODE,
} from '@/constants/upload.constant';
import type {
  CreateAssetRequest,
  PendingUpload,
  SignedUploadForm,
  StorageRequest,
} from '@/interfaces/upload.interface';

const stalledError = (): Error => apiError(0, 'The connection stalled', UPLOAD_STALLED_CODE);

/**
 * Runs an API call that gives up after `UPLOAD_API_TIMEOUT_MS` (a stalled error), while a cancel
 * through `parent` still rejects as the abort it is.
 */
const withTimeout = async <T>(
  call: (signal: AbortSignal) => Promise<T>,
  parent?: AbortSignal,
): Promise<T> => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPLOAD_API_TIMEOUT_MS);
  const forward = (): void => controller.abort(parent?.reason);
  if (parent?.aborted) forward();
  parent?.addEventListener('abort', forward, { once: true });
  try {
    return await call(controller.signal);
  } catch (error) {
    if (controller.signal.aborted && !parent?.aborted) throw stalledError();
    throw error;
  } finally {
    clearTimeout(timer);
    parent?.removeEventListener('abort', forward);
  }
};

/** POST /api/v1/assets: the asset, its first version and the signed form for the file. */
export const createAsset = (
  declaration: CreateAssetRequest,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<PendingUpload> =>
  withTimeout(
    (timed) => apiPost<PendingUpload>(ASSETS_PATH, declaration, { idempotencyKey, signal: timed }),
    signal,
  );

/** POST /api/v1/asset-versions/{id}/completions: the file is in storage, process it. */
export const completeUpload = (versionId: string, signal?: AbortSignal): Promise<unknown> =>
  withTimeout(
    (timed) => apiPost<unknown>(completionsPath(versionId), {}, { signal: timed }),
    signal,
  );

const abortError = (): DOMException => new DOMException('The upload was cancelled', 'AbortError');

/**
 * Sends the file to storage with the signed POST form: every field, then `file` (S3 ignores
 * fields after the file). Uses XMLHttpRequest for upload progress; the browser streams the file.
 */
export const sendToStorage = ({
  form,
  file,
  onProgress,
  signal,
  createRequest = () => new XMLHttpRequest(),
}: {
  form: SignedUploadForm;
  file: File;
  onProgress: (percent: number) => void;
  signal?: AbortSignal;
  createRequest?: () => StorageRequest;
}): Promise<void> =>
  new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const request = createRequest();
    // No progress for `UPLOAD_STALL_MS`: the connection stalled; give the slot back.
    let hasStalled = false;
    let stallTimer: ReturnType<typeof setTimeout> | undefined;
    const watchForStall = (): void => {
      clearTimeout(stallTimer);
      stallTimer = setTimeout(() => {
        hasStalled = true;
        request.abort();
      }, UPLOAD_STALL_MS);
    };
    watchForStall();
    request.upload.addEventListener('progress', (event) => {
      watchForStall();
      if (event.lengthComputable && event.total > 0) onProgress((event.loaded / event.total) * 100);
    });
    request.addEventListener('load', () => {
      clearTimeout(stallTimer);
      if (request.status >= 200 && request.status < 300) resolve();
      else
        reject(
          apiError(
            request.status,
            `Storage refused the file (${String(request.status)})`,
            STORAGE_REJECTED_CODE,
          ),
        );
    });
    request.addEventListener('error', () => {
      clearTimeout(stallTimer);
      reject(apiError(0, 'Storage could not be reached'));
    });
    request.addEventListener('abort', () => {
      clearTimeout(stallTimer);
      reject(hasStalled ? stalledError() : abortError());
    });
    signal?.addEventListener('abort', () => request.abort(), { once: true });

    const body = new FormData();
    for (const [name, value] of Object.entries(form.fields)) body.append(name, value);
    body.append('file', file);
    request.open('POST', form.url);
    request.send(body);
  });
