import type { QueryClient } from '@tanstack/react-query';

/** What every route's `beforeLoad` can use: the app's one query client (KILN-12 guard). */
export interface RouterContext {
  queryClient: QueryClient;
}
