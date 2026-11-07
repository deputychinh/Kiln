import { createRootRouteWithContext, Outlet } from '@tanstack/react-router';

import type { RouterContext } from '@/interfaces/router.interface';

export const Route = createRootRouteWithContext<RouterContext>()({ component: Outlet });
