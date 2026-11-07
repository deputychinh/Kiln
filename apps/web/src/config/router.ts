import type { QueryClient } from '@tanstack/react-query';
import { createRouter, type RegisteredRouter, type RouterHistory } from '@tanstack/react-router';

import { createQueryClient } from '@/config/query-client';
import { ME_QUERY_KEY, SIGN_IN_ROUTE } from '@/constants/auth.constant';
import { routeTree } from '@/routeTree.gen';

const buildRouter = (queryClient: QueryClient, history: RouterHistory | undefined) =>
  createRouter({
    routeTree,
    scrollRestoration: true,
    context: { queryClient },
    ...(history ? { history } : {}),
  });

declare module '@tanstack/react-router' {
  // eslint-disable-next-line no-restricted-syntax -- module augmentation registers the router type
  interface Register {
    router: ReturnType<typeof buildRouter>;
  }
}

/** The router and the query client, wired so a session that ends mid-work leads to sign-in. */
export const createAppRouter = ({
  history,
  retryDelayMs,
}: { history?: RouterHistory; retryDelayMs?: number } = {}): {
  router: RegisteredRouter;
  queryClient: QueryClient;
} => {
  let goToSignIn = (): void => undefined;
  const queryClient = createQueryClient(retryDelayMs, () => goToSignIn());
  const router = buildRouter(queryClient, history);
  goToSignIn = () => {
    const { pathname, href } = router.state.location;
    if (pathname === SIGN_IN_ROUTE) return;
    queryClient.removeQueries({ queryKey: ME_QUERY_KEY });
    void router.navigate({
      to: SIGN_IN_ROUTE,
      search: { redirect: href, expired: true },
      replace: true,
    });
  };
  return { router, queryClient };
};
