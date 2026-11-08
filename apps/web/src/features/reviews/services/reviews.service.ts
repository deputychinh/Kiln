import { apiGet, apiPost } from '@/api/client';
import { REVIEW_PAGE_LIMIT } from '@/constants/reviews.constant';
import type { ReviewEvent, ReviewEventPage, TransitionInput } from '@/interfaces/review.interface';

const API = '/api/v1';
const id = (value: string): string => encodeURIComponent(value);

/** A version's review events, newest first, a page at a time. */
export const listReviewHistory = (
  versionId: string,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<ReviewEventPage> =>
  apiGet<ReviewEventPage>(
    `${API}/asset-versions/${id(versionId)}/review-history?limit=${String(REVIEW_PAGE_LIMIT)}${
      cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''
    }`,
    signal,
  );

/** Approves, requests changes on or reopens a version, if it is still in the expected state. */
export const transitionReview = (
  versionId: string,
  { action, expectedState, note, idempotencyKey }: TransitionInput,
): Promise<ReviewEvent> =>
  apiPost<ReviewEvent>(
    `${API}/asset-versions/${id(versionId)}/review-transitions`,
    { action, expected_state: expectedState, note: note.trim() ? note : null },
    { idempotencyKey },
  );
