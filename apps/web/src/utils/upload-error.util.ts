import { isApiError } from '@/api/client';
import {
  ASSET_KIND_MISMATCH_CODE,
  STORAGE_REJECTED_CODE,
  UPLOAD_STALLED_CODE,
} from '@/constants/upload.constant';
import type { Copy } from '@/interfaces/copy.interface';

const RETRYABLE_CLIENT_STATUSES = new Set([408, 409, 429]);
const BUSY_CODES = new Set(['STORAGE_UNAVAILABLE', 'DATABASE_UNAVAILABLE', 'DATABASE_BUSY']);
const NAME_CODES = new Set(['INVALID_ASSET_NAME', 'INVALID_FILE_NAME']);
const SIZE_CODES = new Set(['INVALID_FILE_SIZE', 'PAYLOAD_TOO_LARGE']);

const refusalOf = (code: string | null, copy: Copy): string => {
  if (code && NAME_CODES.has(code)) return copy.uploads.refused.name;
  if (code && SIZE_CODES.has(code)) return copy.uploads.refused.size;
  if (code === 'UNSUPPORTED_MEDIA_TYPE') return copy.uploads.rejected.unsupported;
  if (code === ASSET_KIND_MISMATCH_CODE) return copy.uploads.refused.kind;
  return copy.uploads.refused.other;
};

/**
 * What a failed upload tells the person, in their language, and whether Retry can help: the
 * API refusing the file (4xx) is final; timeouts, conflicts, rate limits, outages and lost
 * connections are not. Problem titles from the API are English and never shown as they are.
 */
export const uploadFailureOf = (
  error: unknown,
  copy: Copy,
): { error: string; canRetry: boolean } => {
  if (!isApiError(error)) return { error: copy.errors.unexpected, canRetry: true };
  if (error.code === STORAGE_REJECTED_CODE)
    return { error: copy.uploads.storageRejected, canRetry: true };
  if (error.code === UPLOAD_STALLED_CODE) return { error: copy.uploads.stalled, canRetry: true };
  if (error.status === 0) return { error: copy.errors.unreachable, canRetry: true };
  const isClientError = error.status >= 400 && error.status < 500;
  if (isClientError && !RETRYABLE_CLIENT_STATUSES.has(error.status))
    return { error: refusalOf(error.code, copy), canRetry: false };
  if ((error.code && BUSY_CODES.has(error.code)) || isClientError)
    return { error: copy.uploads.busy, canRetry: true };
  return { error: copy.errors.unexpected, canRetry: true };
};
