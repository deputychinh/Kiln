import {
  type InfiniteData,
  useInfiniteQuery,
  type UseInfiniteQueryResult,
  useMutation,
  type UseMutationResult,
  useQueryClient,
} from '@tanstack/react-query';

import { repliesQueryKey, threadsQueryKey } from '@/constants/comments.constant';
import {
  deleteComment,
  editComment,
  listReplies,
  listThreads,
  replyTo,
  setResolved,
  startThread,
} from '@/features/comments/services/comments.service';
import type {
  Comment,
  CommentPage,
  CommentThread,
  ReplyInput,
  StartThreadInput,
  ThreadPage,
} from '@/interfaces/comment.interface';

/**
 * A version's threads, page by page. Other people's comments arrive when the window regains
 * focus (no realtime in v0.2), so focus always refetches.
 */
export const useThreads = (
  versionId: string | undefined,
): UseInfiniteQueryResult<InfiniteData<ThreadPage, string | null>> =>
  useInfiniteQuery({
    queryKey: threadsQueryKey(versionId ?? ''),
    queryFn: ({ pageParam, signal }) => listThreads(versionId ?? '', pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled: versionId !== undefined,
    refetchOnWindowFocus: 'always',
  });

/** A thread's replies, loaded only once the thread is opened. */
export const useReplies = (
  threadId: string,
  isOpen: boolean,
): UseInfiniteQueryResult<InfiniteData<CommentPage, string | null>> =>
  useInfiniteQuery({
    queryKey: repliesQueryKey(threadId),
    queryFn: ({ pageParam, signal }) => listReplies(threadId, pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled: isOpen,
    refetchOnWindowFocus: 'always',
  });

/** Every write refetches the version's threads (and a thread's replies when it touched them). */
const useRefresh = (versionId: string): ((threadId?: string) => Promise<void>) => {
  const queryClient = useQueryClient();
  return async (threadId) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: threadsQueryKey(versionId) }),
      threadId ? queryClient.invalidateQueries({ queryKey: repliesQueryKey(threadId) }) : null,
    ]);
  };
};

export const useStartThread = (
  versionId: string,
): UseMutationResult<CommentThread, Error, StartThreadInput> => {
  const refresh = useRefresh(versionId);
  return useMutation({
    mutationFn: ({ body, region, idempotencyKey }) =>
      startThread(versionId, { body, region }, idempotencyKey),
    onSuccess: () => refresh(),
  });
};

export const useReply = (versionId: string): UseMutationResult<Comment, Error, ReplyInput> => {
  const refresh = useRefresh(versionId);
  return useMutation({
    mutationFn: ({ threadId, body, idempotencyKey }) => replyTo(threadId, body, idempotencyKey),
    onSuccess: (_comment, { threadId }) => refresh(threadId),
  });
};

export const useResolve = (
  versionId: string,
): UseMutationResult<CommentThread, Error, { threadId: string; resolved: boolean }> => {
  const refresh = useRefresh(versionId);
  return useMutation({
    mutationFn: ({ threadId, resolved }) => setResolved(threadId, resolved),
    onSuccess: () => refresh(),
  });
};

export const useEditComment = (
  versionId: string,
): UseMutationResult<Comment, Error, { comment: Comment; body: string }> => {
  const refresh = useRefresh(versionId);
  return useMutation({
    mutationFn: ({ comment, body }) => editComment(comment.id, body),
    onSuccess: (_saved, { comment }) => refresh(comment.thread_id),
  });
};

export const useDeleteComment = (versionId: string): UseMutationResult<void, Error, Comment> => {
  const refresh = useRefresh(versionId);
  return useMutation({
    mutationFn: (comment) => deleteComment(comment.id),
    onSuccess: (_nothing, comment) => refresh(comment.thread_id),
  });
};
