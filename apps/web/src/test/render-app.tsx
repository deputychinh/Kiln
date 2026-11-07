import { type QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryHistory, type RegisteredRouter, RouterProvider } from '@tanstack/react-router';
import { render } from '@testing-library/react';

import { createAppRouter } from '@/config/router';
import { ME_QUERY_KEY } from '@/constants/auth.constant';
import type { Me } from '@/interfaces/auth.interface';
import { aMe } from '@/test/fake-api';

/**
 * Renders the real route tree at `path`, with retries that do not wait, signed in as `aMe()`
 * (pass `me: null` to start signed out, so the app asks the API who is signed in).
 */
export const renderApp = (
  path: string,
  { me = aMe() }: { me?: Me | null } = {},
): { router: RegisteredRouter; queryClient: QueryClient } => {
  const { router, queryClient } = createAppRouter({
    history: createMemoryHistory({ initialEntries: [path] }),
    retryDelayMs: 0,
  });
  if (me) queryClient.setQueryData(ME_QUERY_KEY, me);
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, queryClient };
};
