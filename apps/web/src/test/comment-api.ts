import { act } from '@testing-library/react';

import type { AssetDetail } from '@/interfaces/asset.interface';
import type { CommentServer, SentRequest } from '@/interfaces/comment-server.interface';
import type { Comment, CommentThread, RegionInput } from '@/interfaces/comment.interface';
import { aMe, json, problem, urlOf } from '@/test/fake-api';

const STAMP = '2026-11-06T08:00:00Z';
const ME = aMe();
/** Another person of the studio (not the signed-in one). */
export const anotherPerson = (): Comment['author'] => ({
  id: '0190f1c2-0000-7000-8000-0000000000b0',
  display_name: 'Bo Lead',
});

let sequence = 0;
const nextId = (prefix: string): string => {
  sequence += 1;
  return `${prefix}-${String(sequence)}`;
};

export const aComment = (overrides: Partial<Comment> = {}): Comment => ({
  id: nextId('c'),
  thread_id: 't-1',
  author: { id: ME.id, display_name: ME.display_name },
  body: 'The rim is too bright.',
  created_at: STAMP,
  edited_at: null,
  deleted: false,
  ...overrides,
});

export const aThread = (
  overrides: Partial<CommentThread> & { body?: string; author?: Comment['author'] } = {},
): CommentThread => {
  const { body, author, ...rest } = overrides;
  const id = rest.id ?? nextId('t');
  return {
    id,
    version_id: '0190f1c2-0000-7000-8000-0000000000a1',
    number: 1,
    region: { shape: 'rect', x: 0.25, y: 0.5, width: 0.5, height: 0.25 },
    comment: aComment({
      thread_id: id,
      ...(body === undefined ? {} : { body }),
      ...(author === undefined ? {} : { author }),
    }),
    reply_count: 0,
    resolved_at: null,
    resolved_by: null,
    created_at: STAMP,
    ...rest,
  };
};

const PAGE = 2; // small pages, so "Show more" is easy to reach in tests

/**
 * An in-memory comments API next to a fixed asset: lists page by `PAGE`, creates number threads,
 * PATCH and DELETE change them, everything else answers as the real API would.
 */
export const serveComments = (
  detail: AssetDetail,
  initial: { threads?: Record<string, CommentThread[]>; replies?: Record<string, Comment[]> } = {},
): CommentServer => {
  const threads = new Map(Object.entries(initial.threads ?? {}));
  const replies = new Map(Object.entries(initial.replies ?? {}));
  const sent: SentRequest[] = [];
  const failures: { method: string; prefix: string; response: Response | Error }[] = [];
  const allThreads = (): CommentThread[] => [...threads.values()].flat();
  const findThread = (id: string): CommentThread | undefined =>
    allThreads().find((thread) => thread.id === id);
  const findComment = (id: string): Comment | undefined =>
    [...allThreads().map((thread) => thread.comment), ...[...replies.values()].flat()].find(
      (comment) => comment.id === id,
    );
  const page = <T>(
    items: T[],
    cursor: string | null,
  ): { items: T[]; next_cursor: string | null } => {
    const start = cursor ? Number(cursor) : 0;
    const end = start + PAGE;
    return { items: items.slice(start, end), next_cursor: end < items.length ? String(end) : null };
  };
  const updateComment = (id: string, change: Partial<Comment>): Comment | undefined => {
    for (const list of threads.values()) {
      const thread = list.find((item) => item.comment.id === id);
      if (thread) {
        thread.comment = { ...thread.comment, ...change };
        return thread.comment;
      }
    }
    for (const list of replies.values()) {
      const index = list.findIndex((item) => item.id === id);
      const found = list[index];
      if (found) {
        list[index] = { ...found, ...change };
        return list[index];
      }
    }
    return undefined;
  };

  const handle = (method: string, path: string, body: unknown): Response => {
    const [pathname = '', search = ''] = path.split('?');
    const cursor = new URLSearchParams(search).get('cursor');
    if (pathname === `/api/v1/assets/${detail.id}`) return json(detail);
    if (pathname.startsWith('/api/v1/assets')) return json({ items: [detail], next_cursor: null });
    const versionMatch = /^\/api\/v1\/asset-versions\/([^/]+)\/comment-threads$/.exec(pathname);
    if (versionMatch?.[1]) {
      const versionId = decodeURIComponent(versionMatch[1]);
      const list = threads.get(versionId) ?? [];
      if (method === 'GET') return json(page(list, cursor));
      const request = body as { body: string; region: RegionInput | null };
      const id = nextId('t');
      const thread = aThread({
        id,
        version_id: versionId,
        number: list.length + 1,
        body: request.body.trim(),
        region: request.region
          ? {
              shape: request.region.shape,
              x: request.region.x,
              y: request.region.y,
              width: request.region.width ?? null,
              height: request.region.height ?? null,
            }
          : null,
      });
      threads.set(versionId, [...list, thread]);
      return json(thread, 201);
    }
    const repliesMatch = /^\/api\/v1\/comment-threads\/([^/]+)\/comments$/.exec(pathname);
    if (repliesMatch?.[1]) {
      const threadId = repliesMatch[1];
      const list = replies.get(threadId) ?? [];
      if (method === 'GET') return json(page(list, cursor));
      const reply = aComment({ thread_id: threadId, body: (body as { body: string }).body });
      replies.set(threadId, [...list, reply]);
      const thread = findThread(threadId);
      if (thread) thread.reply_count += 1;
      return json(reply, 201);
    }
    const threadMatch = /^\/api\/v1\/comment-threads\/([^/]+)$/.exec(pathname);
    if (threadMatch?.[1] && method === 'PATCH') {
      const thread = findThread(threadMatch[1]);
      if (!thread) return problem(404, 'Not Found', 'COMMENT_THREAD_NOT_FOUND');
      const resolved = (body as { resolved: boolean }).resolved;
      thread.resolved_at = resolved ? STAMP : null;
      thread.resolved_by = resolved ? { id: ME.id, display_name: ME.display_name } : null;
      return json(thread);
    }
    const commentMatch = /^\/api\/v1\/comments\/([^/]+)$/.exec(pathname);
    if (commentMatch?.[1]) {
      const comment = findComment(commentMatch[1]);
      if (!comment) return problem(404, 'Not Found', 'COMMENT_NOT_FOUND');
      if (comment.author.id !== ME.id) return problem(403, 'Forbidden', 'NOT_COMMENT_AUTHOR');
      if (method === 'DELETE') {
        updateComment(comment.id, { body: '', deleted: true });
        return new Response(null, { status: 204 });
      }
      return json(
        updateComment(comment.id, {
          body: (body as { body: string }).body.trim(),
          edited_at: STAMP,
        }),
      );
    }
    return problem(404, 'Not Found', 'NOT_FOUND');
  };

  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = new URL(urlOf(input));
    const path = `${url.pathname}${url.search}`;
    const method = init?.method ?? 'GET';
    const body: unknown = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    const headers = new Headers(init?.headers);
    sent.push({ method, path, body, idempotencyKey: headers.get('Idempotency-Key') });
    const failure = failures.findIndex(
      (item) => item.method === method && path.startsWith(item.prefix),
    );
    if (failure >= 0) {
      const [{ response }] = failures.splice(failure, 1) as [(typeof failures)[number]];
      return response instanceof Error ? Promise.reject(response) : Promise.resolve(response);
    }
    return Promise.resolve(handle(method, path, body));
  });

  return {
    fetchMock,
    threads,
    replies,
    sent,
    failNext: (failMethod, prefix, response) =>
      failures.push({ method: failMethod, prefix, response }),
    requests: (method, prefix) =>
      sent.filter((request) => request.method === method && request.path.startsWith(prefix)),
  };
};

/** jsdom never loads images: report the preview as loaded at `width` × `height`. */
export const loadImage = (image: HTMLElement, width = 800, height = 400): void => {
  Object.defineProperty(image, 'naturalWidth', { configurable: true, value: width });
  Object.defineProperty(image, 'naturalHeight', { configurable: true, value: height });
  act(() => {
    image.dispatchEvent(new Event('load'));
  });
};
