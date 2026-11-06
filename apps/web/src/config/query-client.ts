import { QueryClient } from '@tanstack/react-query';

import { isApiError } from '@/api/client';
import { QUERY_MAX_RETRIES, QUERY_STALE_MS } from '@/constants/query.constant';

const HTTP_CLIENT_ERROR_MIN = 400;
const HTTP_SERVER_ERROR_MIN = 500;

/** Retry only what can succeed later: network errors and 5xx, never a 4xx answer. */
export const shouldRetry = (failureCount: number, error: unknown): boolean => {
  const isClientError =
    isApiError(error) &&
    error.status >= HTTP_CLIENT_ERROR_MIN &&
    error.status < HTTP_SERVER_ERROR_MIN;
  return !isClientError && failureCount < QUERY_MAX_RETRIES;
};

export const createQueryClient = (retryDelayMs?: number): QueryClient =>
  new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: QUERY_STALE_MS,
        retry: shouldRetry,
        ...(retryDelayMs === undefined ? {} : { retryDelay: retryDelayMs }),
      },
    },
  });
