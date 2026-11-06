import { isApiError } from '@/api/client';
import type { Copy } from '@/interfaces/copy.interface';

const HTTP_NOT_FOUND = 404;
const HTTP_UNPROCESSABLE = 422;

/** The sentence a person sees for a failed request. */
export const describeError = (error: unknown, copy: Copy): string => {
  if (isApiError(error) && error.status === 0) return copy.errors.unreachable;
  if (error instanceof Error && error.message) return error.message;
  return copy.errors.unexpected;
};

/** An unknown id (404) or one that is not a UUID (422): retrying cannot help. */
export const isNotFound = (error: unknown): boolean =>
  isApiError(error) && (error.status === HTTP_NOT_FOUND || error.status === HTTP_UNPROCESSABLE);
