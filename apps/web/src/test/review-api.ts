import { REVIEW_ACTIONS, REVIEW_DECISIONS } from '@/constants/reviews.constant';
import type { AssetDetail } from '@/interfaces/asset.interface';
import type { SentRequest } from '@/interfaces/comment-server.interface';
import type { ReviewServer } from '@/interfaces/review-server.interface';
import type { ReviewAction, ReviewEvent, ReviewState } from '@/interfaces/review.interface';
import { aMe, json, urlOf } from '@/test/fake-api';

const STAMP = '2026-11-06T08:00:00Z';
const ME = aMe();
const PAGE = 2; // small pages, so "Show older" is easy to reach in tests
const NEXT_STATE: Record<ReviewAction, ReviewState> = {
  approve: 'approved',
  request_changes: 'changes_requested',
  reopen: 'in_review',
};

let sequence = 0;

export const aReviewEvent = (overrides: Partial<ReviewEvent> = {}): ReviewEvent => {
  sequence += 1;
  return {
    id: `e-${String(sequence)}`,
    version_id: 'v-1',
    sequence: 1,
    action: 'approve',
    from_state: 'in_review',
    to_state: 'approved',
    actor: { id: ME.id, display_name: ME.display_name },
    note: null,
    created_at: STAMP,
    ...overrides,
  };
};

const conflict = (code: string, currentState: ReviewState): Response =>
  new Response(
    JSON.stringify({
      type: 'about:blank',
      title: 'Conflict',
      status: 409,
      code,
      current_state: currentState,
    }),
    { status: 409, headers: { 'Content-Type': 'application/problem+json' } },
  );

/**
 * An in-memory reviews API next to one asset: the transition table and the ready rule of the
 * real API, a compare-and-set on `expected_state`, and the history newest first by `PAGE`.
 */
export const serveReviews = (
  detail: AssetDetail,
  initial: Record<string, ReviewEvent[]> = {},
): ReviewServer => {
  const asset: AssetDetail = structuredClone(detail);
  const history = new Map(Object.entries(initial));
  const sent: SentRequest[] = [];
  const failures: { method: string; prefix: string; response: Response | Error }[] = [];

  const apply = ({
    versionId,
    action,
    note,
    by = ME,
  }: {
    versionId: string;
    action: ReviewAction;
    note: string | null;
    by?: typeof ME;
  }): ReviewEvent => {
    const version = asset.versions.find((item) => item.id === versionId);
    if (!version) throw new Error(`no version ${versionId}`);
    const event = aReviewEvent({
      version_id: versionId,
      sequence: version.review_revision + 1,
      action,
      from_state: version.review_state,
      to_state: NEXT_STATE[action],
      actor: { id: by.id, display_name: by.display_name },
      note,
    });
    version.review_state = event.to_state;
    version.review_revision = event.sequence;
    const newest = asset.versions.at(-1);
    if (newest) asset.review_state = newest.review_state;
    history.set(versionId, [event, ...(history.get(versionId) ?? [])]);
    return event;
  };

  const handle = (method: string, path: string, body: unknown): Response => {
    const [pathname = '', search = ''] = path.split('?');
    if (pathname === `/api/v1/assets/${asset.id}`) return json(asset);
    if (pathname.startsWith('/api/v1/assets')) return json({ items: [asset], next_cursor: null });
    const historyMatch = /^\/api\/v1\/asset-versions\/([^/]+)\/review-history$/.exec(pathname);
    if (historyMatch?.[1]) {
      const list = history.get(historyMatch[1]) ?? [];
      const start = Number(new URLSearchParams(search).get('cursor') ?? 0);
      const end = start + PAGE;
      return json({
        items: list.slice(start, end),
        next_cursor: end < list.length ? String(end) : null,
      });
    }
    const transitionMatch = /^\/api\/v1\/asset-versions\/([^/]+)\/review-transitions$/.exec(
      pathname,
    );
    if (transitionMatch?.[1] && method === 'POST') {
      const versionId = transitionMatch[1];
      const version = asset.versions.find((item) => item.id === versionId);
      const request = body as {
        action: ReviewAction;
        expected_state: ReviewState;
        note: string | null;
      };
      if (!version) return json({ code: 'ASSET_VERSION_NOT_FOUND' }, 404);
      if (version.review_state !== request.expected_state) {
        return conflict('REVIEW_STATE_CONFLICT', version.review_state);
      }
      if (!REVIEW_ACTIONS[version.review_state].includes(request.action)) {
        return conflict('INVALID_REVIEW_TRANSITION', version.review_state);
      }
      if (REVIEW_DECISIONS.includes(request.action) && version.status !== 'ready') {
        return conflict('VERSION_NOT_READY', version.review_state);
      }
      return json(
        apply({ versionId, action: request.action, note: request.note?.trim() ?? null }),
        201,
      );
    }
    return json({ code: 'NOT_FOUND' }, 404);
  };

  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = new URL(urlOf(input));
    const path = `${url.pathname}${url.search}`;
    const method = init?.method ?? 'GET';
    const parsed: unknown = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    const headers = new Headers(init?.headers);
    sent.push({ method, path, body: parsed, idempotencyKey: headers.get('Idempotency-Key') });
    const failure = failures.findIndex(
      (item) => item.method === method && path.startsWith(item.prefix),
    );
    if (failure >= 0) {
      const [{ response }] = failures.splice(failure, 1) as [(typeof failures)[number]];
      return response instanceof Error ? Promise.reject(response) : Promise.resolve(response);
    }
    return Promise.resolve(handle(method, path, parsed));
  });

  return {
    fetchMock,
    sent,
    decideAsSomeoneElse: (versionId, action) => {
      apply({
        versionId,
        action,
        note: null,
        by: { ...ME, id: 'someone-else', display_name: 'Bo Lead' },
      });
    },
    failNext: (failMethod, prefix, response) =>
      failures.push({ method: failMethod, prefix, response }),
    requests: (method, prefix) =>
      sent.filter((request) => request.method === method && request.path.startsWith(prefix)),
  };
};
