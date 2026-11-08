import {
  type InfiniteData,
  useInfiniteQuery,
  type UseInfiniteQueryResult,
  useMutation,
  type UseMutationResult,
  useQueryClient,
} from '@tanstack/react-query';

import { ASSET_LIST_QUERY_KEY, assetDetailQueryKey } from '@/constants/assets.constant';
import { reviewHistoryQueryKey } from '@/constants/reviews.constant';
import { listReviewHistory, transitionReview } from '@/features/reviews/services/reviews.service';
import type { ReviewEvent, ReviewEventPage, TransitionInput } from '@/interfaces/review.interface';

/** A version's review history, newest first; other people's decisions arrive on focus. */
export const useReviewHistory = (
  versionId: string | undefined,
): UseInfiniteQueryResult<InfiniteData<ReviewEventPage, string | null>> =>
  useInfiniteQuery({
    queryKey: reviewHistoryQueryKey(versionId ?? ''),
    queryFn: ({ pageParam, signal }) => listReviewHistory(versionId ?? '', pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled: versionId !== undefined,
    refetchOnWindowFocus: 'always',
  });

/**
 * A decision on one version. Success or failure, the asset (its versions' states), the gallery
 * (the asset's state) and the history are fetched again: after a conflict they show who won.
 */
export const useReviewTransition = (
  assetId: string,
  versionId: string,
): UseMutationResult<ReviewEvent, Error, TransitionInput> => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input) => transitionReview(versionId, input),
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: assetDetailQueryKey(assetId) }),
        queryClient.invalidateQueries({ queryKey: ASSET_LIST_QUERY_KEY }),
        queryClient.invalidateQueries({ queryKey: reviewHistoryQueryKey(versionId) }),
      ]),
  });
};
