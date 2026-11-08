import { isApiError } from '@/api/client';
import { REVIEW_ACTIONS, REVIEW_DECISIONS, REVIEW_STATES } from '@/constants/reviews.constant';
import type { AssetVersion } from '@/interfaces/asset.interface';
import type { Copy } from '@/interfaces/copy.interface';
import type { ReviewAction, ReviewState } from '@/interfaces/review.interface';
import { describeError } from '@/utils/error.util';

/** What can be done to a version now: the state machine's actions, decisions only when ready. */
export const availableActions = (version: AssetVersion): readonly ReviewAction[] =>
  REVIEW_ACTIONS[version.review_state].filter(
    (action) => version.status === 'ready' || !REVIEW_DECISIONS.includes(action),
  );

const isReviewState = (value: string | null): value is ReviewState =>
  REVIEW_STATES.includes(value as ReviewState);

/** The sentence for a failed decision: who won a conflict, or what the API's code means. */
export const reviewErrorMessage = (error: unknown, copy: Copy): string => {
  const { errors } = copy.reviews;
  if (!isApiError(error)) return describeError(error, copy);
  if (error.code === 'REVIEW_STATE_CONFLICT' && isReviewState(error.currentState)) {
    return copy.reviews.conflict(copy.reviews.state[error.currentState]);
  }
  const byCode: Record<string, string> = {
    INVALID_REVIEW_NOTE: errors.invalidNote,
    VERSION_NOT_READY: errors.notReady,
    INVALID_REVIEW_TRANSITION: errors.transition,
    REVIEW_STATE_CONFLICT: errors.transition,
    INSUFFICIENT_SCOPE: errors.readOnly,
    ASSET_VERSION_NOT_FOUND: errors.gone,
  };
  return (error.code !== null ? byCode[error.code] : undefined) ?? describeError(error, copy);
};
