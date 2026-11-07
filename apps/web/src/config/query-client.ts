import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';

import { isApiError } from '@/api/client';
import { ME_QUERY_KEY } from '@/constants/auth.constant';
import { QUERY_MAX_RETRIES, QUERY_STALE_MS } from '@/constants/query.constant';
import { isSignedOut } from '@/utils/auth.util';

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

/**
 * The app's query client. `onSignedOut` runs when any request answers 401 `UNAUTHENTICATED`
 * (the session expired or was ended elsewhere), so the person lands on sign-in (KILN-12).
 */
export const createQueryClient = (
  retryDelayMs?: number,
  onSignedOut: () => void = () => undefined,
): QueryClient => {
  const onError = (error: unknown): void => {
    if (isSignedOut(error)) onSignedOut();
  };
  return new QueryClient({
    // Who-is-signed-in itself is the route guard's business (a first visit is not an expiry).
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (query.queryKey !== ME_QUERY_KEY && query.queryKey.join() !== ME_QUERY_KEY.join()) {
          onError(error);
        }
      },
    }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: {
      queries: {
        staleTime: QUERY_STALE_MS,
        retry: shouldRetry,
        ...(retryDelayMs === undefined ? {} : { retryDelay: retryDelayMs }),
      },
    },
  });
};
