import { createRootRoute, Outlet } from '@tanstack/react-router';

import { AppShell } from '@/components/AppShell/AppShell';
import { UPLOAD_BUTTON_ID } from '@/constants/upload.constant';
import { UploadButton } from '@/features/uploads/components/UploadButton';
import { UploadDropOverlay } from '@/features/uploads/components/UploadDropOverlay';
import { UploadTray } from '@/features/uploads/components/UploadTray';
import { UploadsProvider } from '@/features/uploads/context/UploadsContext';

export const Route = createRootRoute({
  component: () => (
    // Uploads belong to the app, not a page: they keep running on any route (KILN-8, KILN-30),
    // start from the top bar or a drop anywhere, and show in the tray (KILN-35).
    <UploadsProvider>
      <AppShell
        actions={<UploadButton id={UPLOAD_BUTTON_ID} />}
        overlays={
          <>
            <UploadTray />
            <UploadDropOverlay />
          </>
        }
      >
        <Outlet />
      </AppShell>
    </UploadsProvider>
  ),
});
