import { apiError, apiPost } from '@/api/client';
import { ASSETS_PATH } from '@/constants/assets.constant';
import { completionsPath, STORAGE_REJECTED_CODE } from '@/constants/upload.constant';
import type {
  CreateAssetRequest,
  PendingUpload,
  SignedUploadForm,
  StorageRequest,
} from '@/interfaces/upload.interface';

/** POST /api/v1/assets: the asset, its first version and the signed form for the file. */
export const createAsset = (
  declaration: CreateAssetRequest,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<PendingUpload> =>
  apiPost<PendingUpload>(ASSETS_PATH, declaration, {
    idempotencyKey,
    ...(signal ? { signal } : {}),
  });

/** POST /api/v1/asset-versions/{id}/completions: the file is in storage, process it. */
export const completeUpload = (versionId: string, signal?: AbortSignal): Promise<unknown> =>
  apiPost<unknown>(completionsPath(versionId), {}, signal ? { signal } : {});

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
    request.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable && event.total > 0) onProgress((event.loaded / event.total) * 100);
    });
    request.addEventListener('load', () => {
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
    request.addEventListener('error', () => reject(apiError(0, 'Storage could not be reached')));
    request.addEventListener('abort', () => reject(abortError()));
    signal?.addEventListener('abort', () => request.abort(), { once: true });

    const body = new FormData();
    for (const [name, value] of Object.entries(form.fields)) body.append(name, value);
    body.append('file', file);
    request.open('POST', form.url);
    request.send(body);
  });
