import { apiDelete, apiGet, apiPatch, apiPost } from '@/api/client';
import { COMMENT_PAGE_LIMIT } from '@/constants/comments.constant';
import type {
  Comment,
  CommentPage,
  CommentThread,
  RegionInput,
  ThreadPage,
} from '@/interfaces/comment.interface';

const API = '/api/v1';
const pageQuery = (cursor: string | null): string =>
  `?limit=${String(COMMENT_PAGE_LIMIT)}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`;
const id = (value: string): string => encodeURIComponent(value);

/** A version's threads by number, a page at a time. */
export const listThreads = (
  versionId: string,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<ThreadPage> =>
  apiGet<ThreadPage>(
    `${API}/asset-versions/${id(versionId)}/comment-threads${pageQuery(cursor)}`,
    signal,
  );

/** Starts a thread; the key makes a retry of the same draft replay instead of posting twice. */
export const startThread = (
  versionId: string,
  request: { body: string; region: RegionInput | null },
  idempotencyKey: string,
): Promise<CommentThread> =>
  apiPost<CommentThread>(`${API}/asset-versions/${id(versionId)}/comment-threads`, request, {
    idempotencyKey,
  });

/** A thread's replies oldest first, a page at a time. */
export const listReplies = (
  threadId: string,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<CommentPage> =>
  apiGet<CommentPage>(
    `${API}/comment-threads/${id(threadId)}/comments${pageQuery(cursor)}`,
    signal,
  );

/** Replies at the end of a thread (idempotent per key, like a new thread). */
export const replyTo = (threadId: string, body: string, idempotencyKey: string): Promise<Comment> =>
  apiPost<Comment>(`${API}/comment-threads/${id(threadId)}/comments`, { body }, { idempotencyKey });

/** Resolves or reopens a thread. */
export const setResolved = (threadId: string, resolved: boolean): Promise<CommentThread> =>
  apiPatch<CommentThread>(`${API}/comment-threads/${id(threadId)}`, { resolved });

/** Changes the text of your own comment. */
export const editComment = (commentId: string, body: string): Promise<Comment> =>
  apiPatch<Comment>(`${API}/comments/${id(commentId)}`, { body });

/** Deletes your own comment (it stays in its thread as deleted). */
export const deleteComment = (commentId: string): Promise<void> =>
  apiDelete(`${API}/comments/${id(commentId)}`);
