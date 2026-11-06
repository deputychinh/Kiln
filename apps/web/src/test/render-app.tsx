import { type QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  createMemoryHistory,
  createRouter,
  type RegisteredRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { render } from '@testing-library/react';

import { createQueryClient } from '@/config/query-client';
import { routeTree } from '@/routeTree.gen';

/** Renders the real route tree at `path`, with retries that do not wait. */
export const renderApp = (path: string): { router: RegisteredRouter; queryClient: QueryClient } => {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
  });
  const queryClient = createQueryClient(0);
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, queryClient };
};
