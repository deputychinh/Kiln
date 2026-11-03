import '@kiln/ui/tokens.css';
import '@/styles/base.css';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createRouter, RouterProvider } from '@tanstack/react-router';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { QUERY_STALE_MS } from '@/constants/query.constant';
import { routeTree } from '@/routeTree.gen';

const router = createRouter({ routeTree });
const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: QUERY_STALE_MS } } });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root element');

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
