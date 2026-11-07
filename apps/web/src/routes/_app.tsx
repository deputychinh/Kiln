import { createFileRoute, Outlet, redirect } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';

import { AppShell } from '@/components/AppShell/AppShell';
import { UPLOAD_BUTTON_ID } from '@/constants/upload.constant';
import { UserMenu } from '@/features/auth/components/UserMenu';
import { meQueryOptions } from '@/features/auth/services/me.query';
import { UploadButton } from '@/features/uploads/components/UploadButton';
import { UploadDropOverlay } from '@/features/uploads/components/UploadDropOverlay';
import { UploadsProvider } from '@/features/uploads/context/UploadsContext';
import { isSignedOut } from '@/utils/auth.util';

// The tray shows only once files are added: its code loads after the first screen.
const UploadTray = lazy(() =>
  import('@/features/uploads/components/UploadTray').then((module) => ({
    default: module.UploadTray,
  })),
);

const AppLayout = (): React.ReactElement => (
  // Uploads belong to the app, not a page: they keep running on any route (KILN-8, KILN-30),
  // start from the top bar or a drop anywhere, and show in the tray (KILN-35).
  <UploadsProvider>
    <AppShell
      actions={<UploadButton id={UPLOAD_BUTTON_ID} />}
      account={<UserMenu />}
      overlays={
        <>
          <Suspense fallback={null}>
            <UploadTray />
          </Suspense>
          <UploadDropOverlay />
        </>
      }
    >
      <Outlet />
    </AppShell>
  </UploadsProvider>
);

/**
 * Everything behind sign-in (KILN-12). Signed out, the page goes to `/sign-in` and keeps where it
 * was going; any other failure lets the shell render so each view shows its own error and retry.
 */
export const Route = createFileRoute('/_app')({
  beforeLoad: async ({ context, location }) => {
    try {
      await context.queryClient.ensureQueryData(meQueryOptions());
    } catch (error) {
      if (isSignedOut(error)) {
        redirect({
          to: '/sign-in',
          search: { redirect: location.href },
          replace: true,
          throw: true,
        });
      }
    }
  },
  component: AppLayout,
});
