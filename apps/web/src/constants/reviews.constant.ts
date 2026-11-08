import { BadgeTone } from '@kiln/ui';

import type { ReviewAction, ReviewState } from '@/interfaces/review.interface';

/** The API's limit on one review note (KILN-11); the field stops at it. */
export const REVIEW_NOTE_MAX_LENGTH = 1000;
/** History events per request (the API allows 1 to 100). */
export const REVIEW_PAGE_LIMIT = 20;
export const reviewHistoryQueryKey = (versionId: string) => ['review-history', versionId] as const;

/** The tone that reinforces each state's icon and word (never the only signal, WCAG 1.4.1). */
export const REVIEW_STATE_TONE: Record<ReviewState, BadgeTone> = {
  in_review: BadgeTone.Info,
  approved: BadgeTone.Success,
  changes_requested: BadgeTone.Warning,
};

/** The actions the state machine allows from each state (domain/reviews.py, ADR 0015). */
export const REVIEW_ACTIONS: Record<ReviewState, readonly ReviewAction[]> = {
  in_review: ['approve', 'request_changes'],
  approved: ['reopen'],
  changes_requested: ['reopen'],
};

/** Actions that decide, and so need a ready version; reopening does not. */
export const REVIEW_DECISIONS: readonly ReviewAction[] = ['approve', 'request_changes'];

/** "Needs attention" order: what to fix, then what to look at, then what is done. */
export const REVIEW_ATTENTION_ORDER: Record<ReviewState, number> = {
  changes_requested: 0,
  in_review: 1,
  approved: 2,
};

export const REVIEW_STATES: readonly ReviewState[] = ['in_review', 'changes_requested', 'approved'];
