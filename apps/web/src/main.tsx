import '@fontsource-variable/inter/wght.css';
import '@kiln/ui/tokens.css';
import '@/styles/base.css';

import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from '@tanstack/react-router';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { createAppRouter } from '@/config/router';
import { applyStoredTheme } from '@/utils/theme.util';

const { router, queryClient } = createAppRouter();

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
