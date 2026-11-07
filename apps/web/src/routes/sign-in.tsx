import { createFileRoute, redirect } from '@tanstack/react-router';
import type { ReactElement } from 'react';

import { SignInPage } from '@/features/auth/components/SignInPage';
import { meQueryOptions } from '@/features/auth/services/me.query';
import { parseSignInSearch, safeRedirect } from '@/utils/redirect.util';

const SignInRoute = (): ReactElement => {
  const { redirect: target, expired } = Route.useSearch();
  return <SignInPage redirect={target} isExpired={expired === true} />;
};

/** The only page outside the app shell; someone already signed in goes straight on. */
export const Route = createFileRoute('/sign-in')({
  validateSearch: parseSignInSearch,
  beforeLoad: async ({ context, search }) => {
    const signedIn = await context.queryClient
      .ensureQueryData(meQueryOptions())
      .then(() => true)
      .catch(() => false);
    if (signedIn) redirect({ href: safeRedirect(search.redirect), replace: true, throw: true });
  },
  component: SignInRoute,
});
