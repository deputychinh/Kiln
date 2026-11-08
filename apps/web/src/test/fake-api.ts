import type { MockInstance } from 'vitest';

import type { Asset, AssetDetail, AssetVersion } from '@/interfaces/asset.interface';
import type { AccessToken, Me } from '@/interfaces/auth.interface';

type Reply = Response | (() => Response) | Error;
type FetchMock = MockInstance<typeof fetch>;

/** The URL of a `fetch` call, whatever form its input took. */
export const urlOf = (input: unknown): string => {
  if (input instanceof Request) return input.url;
  if (input instanceof URL) return input.href;
  return typeof input === 'string' ? input : '';
};

/** How many requests went to a URL ending with `path`. */
export const countRequests = (fetchMock: FetchMock, path: string): number =>
  fetchMock.mock.calls.filter(([input]) => urlOf(input).endsWith(path)).length;

export const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

export const problem = (status: number, title: string, code: string): Response =>
  new Response(JSON.stringify({ type: 'about:blank', title, status, code }), {
    status,
    headers: { 'Content-Type': 'application/problem+json' },
  });

/**
 * Replaces `fetch` with a queue of replies per path prefix (longest prefix wins); the last reply
 * of a queue repeats. Returns the mock so tests can count and inspect requests.
 */
export const fakeApi = (routes: Record<string, Reply[]>): FetchMock => {
  const queues = new Map(Object.entries(routes).map(([path, replies]) => [path, [...replies]]));
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const url = new URL(urlOf(input));
    const path = `${url.pathname}${url.search}`;
    const key = [...queues.keys()]
      .filter((prefix) => path.startsWith(prefix))
      .sort((a, b) => b.length - a.length)[0];
    const queue = key === undefined ? undefined : queues.get(key);
    const reply = queue && queue.length > 1 ? queue.shift() : queue?.[0];
    if (reply === undefined) return Promise.reject(new Error(`No fake reply for ${path}`));
    if (reply instanceof Error) return Promise.reject(reply);
    return Promise.resolve(typeof reply === 'function' ? reply() : reply.clone());
  });
};

const STAMP = '2026-11-06T08:00:00Z';

export const aMe = (overrides: Partial<Me> = {}): Me => ({
  id: '0190f1c2-0000-7000-8000-0000000000f1',
  email: 'ada@kiln.test',
  display_name: 'Ada Artist',
  auth_method: 'session',
  scopes: ['read', 'write'],
  ...overrides,
});

export const aToken = (overrides: Partial<AccessToken> = {}): AccessToken => ({
  id: '0190f1c2-0000-7000-8000-0000000000c1',
  name: 'Blender laptop',
  prefix: 'kiln_pat_Ab3dEf',
  scopes: ['read', 'write'],
  created_at: STAMP,
  expires_at: '2027-02-04T08:00:00Z',
  last_used_at: null,
  ...overrides,
});

/** A SigV4-style presigned URL of `key`, signed at `amzDate` for 15 minutes. */
export const signedUrl = (key: string, amzDate: string): string =>
  `http://s3.test/kiln/${key}?X-Amz-Date=${amzDate}&X-Amz-Expires=900&X-Amz-Signature=${amzDate}`;

export const anAsset = (overrides: Partial<Asset> = {}): Asset => ({
  id: '0190f1c2-0000-7000-8000-000000000001',
  name: 'rock_albedo',
  kind: 'image',
  created_at: STAMP,
  updated_at: STAMP,
  thumbnail_url: 'http://s3.test/thumbs/rock.webp?sig=1',
  review_state: 'in_review',
  ...overrides,
});

export const aVersion = (overrides: Partial<AssetVersion> = {}): AssetVersion => ({
  id: '0190f1c2-0000-7000-8000-0000000000a1',
  asset_id: '0190f1c2-0000-7000-8000-000000000001',
  number: 1,
  status: 'ready',
  file_name: 'rock_albedo.png',
  content_type: 'image/png',
  size_bytes: 1_500_000,
  created_at: STAMP,
  updated_at: STAMP,
  failure_reason: null,
  thumbnail_url: 'http://s3.test/thumbs/rock.webp?sig=1',
  review_state: 'in_review',
  review_revision: 0,
  ...overrides,
});

export const aDetail = (overrides: Partial<AssetDetail> = {}): AssetDetail => ({
  ...anAsset(),
  versions: [aVersion()],
  ...overrides,
});
