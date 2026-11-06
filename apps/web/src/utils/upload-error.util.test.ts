import { apiError } from '@/api/client';
import { STORAGE_REJECTED_CODE } from '@/constants/upload.constant';
import { en } from '@/locales/en';
import { uploadFailureOf } from '@/utils/upload-error.util';

describe('uploadFailureOf', () => {
  it.each([
    [apiError(0, 'Failed to fetch'), en.errors.unreachable],
    [apiError(403, 'Forbidden', STORAGE_REJECTED_CODE), en.uploads.storageRejected],
    [apiError(503, 'Storage is unavailable', 'STORAGE_UNAVAILABLE'), en.uploads.busy],
    [apiError(503, 'Database is busy', 'DATABASE_BUSY'), en.uploads.busy],
    [apiError(429, 'Too Many Requests'), en.uploads.busy],
    [apiError(408, 'Request Timeout'), en.uploads.busy],
    [apiError(409, 'Idempotency key in use', 'IDEMPOTENCY_KEY_IN_USE'), en.uploads.busy],
    [apiError(500, 'Internal Server Error', 'INTERNAL'), en.errors.unexpected],
    [new Error('boom'), en.errors.unexpected],
  ])('lets %s be retried, saying %j', (error, message) => {
    expect(uploadFailureOf(error, en)).toEqual({ error: message, canRetry: true });
  });

  it.each([
    [apiError(422, 'Unprocessable Entity', 'VALIDATION_FAILED'), en.uploads.refused.other],
    [apiError(422, 'Invalid name', 'INVALID_ASSET_NAME'), en.uploads.refused.name],
    [apiError(422, 'Invalid file name', 'INVALID_FILE_NAME'), en.uploads.refused.name],
    [apiError(415, 'Unsupported', 'UNSUPPORTED_MEDIA_TYPE'), en.uploads.rejected.unsupported],
    [apiError(422, 'Invalid size', 'INVALID_FILE_SIZE'), en.uploads.refused.size],
    [apiError(413, 'Too large', 'PAYLOAD_TOO_LARGE'), en.uploads.refused.size],
    [apiError(400, 'Bad Request'), en.uploads.refused.other],
  ])('does not offer a retry that cannot help for %s, saying %j', (error, message) => {
    expect(uploadFailureOf(error, en)).toEqual({ error: message, canRetry: false });
  });
});
