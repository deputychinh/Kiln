import type { MockInstance } from 'vitest';

import { urlOf } from '@/test/fake-api';

type Handler = (method: string, path: string, body: unknown) => Response | Promise<Response>;

/** Replaces `fetch` with a handler that sees the method, the path and the parsed JSON body. */
export const routeApi = (handler: Handler): MockInstance<typeof fetch> =>
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(urlOf(input));
    const body: unknown = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    const reply = await handler(init?.method ?? 'GET', `${url.pathname}${url.search}`, body);
    return reply.clone();
  });
