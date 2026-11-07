import { ME_QUERY_KEY, ME_STALE_MS } from '@/constants/auth.constant';
import { getMe } from '@/features/auth/services/auth.service';
import type { Me } from '@/interfaces/auth.interface';

/** The one definition of the signed-in user query (route guard, user menu). */
export const meQueryOptions = (): {
  queryKey: typeof ME_QUERY_KEY;
  queryFn: (context: { signal: AbortSignal }) => Promise<Me>;
  staleTime: number;
} => ({
  queryKey: ME_QUERY_KEY,
  queryFn: ({ signal }) => getMe(signal),
  staleTime: ME_STALE_MS,
});
