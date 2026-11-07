import '@fontsource-variable/inter/wght.css';
import '@kiln/ui/tokens.css';
import '@/styles/base.css';

import { QueryClientProvider } from '@tanstack/react-query';
import { createRouter, RouterProvider } from '@tanstack/react-router';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { createQueryClient } from '@/config/query-client';
import { routeTree } from '@/routeTree.gen';
import { applyStoredTheme } from '@/utils/theme.util';

const router = createRouter({ routeTree, scrollRestoration: true });
const queryClient = createQueryClient();

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

// A theme chosen earlier applies before the first render (no inline script: the CSP forbids it).
applyStoredTheme();

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root element');

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
