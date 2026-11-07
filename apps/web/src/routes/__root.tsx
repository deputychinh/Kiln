import { createRootRoute, Outlet } from '@tanstack/react-router';

import { AppShell } from '@/components/AppShell/AppShell';
import { UploadsProvider } from '@/features/uploads/context/UploadsContext';

export const Route = createRootRoute({
  component: () => (
    // Uploads belong to the app, not a page: they keep running on any route (KILN-8, KILN-30).
    <UploadsProvider>
      <AppShell>
        <Outlet />
      </AppShell>
    </UploadsProvider>
  ),
});
