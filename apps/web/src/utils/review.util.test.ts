import { apiError } from '@/api/client';
import type { VersionStatus } from '@/interfaces/asset.interface';
import type { ReviewAction, ReviewState } from '@/interfaces/review.interface';
import { en } from '@/locales/en';
import { aVersion } from '@/test/fake-api';
import { availableActions, reviewErrorMessage } from '@/utils/review.util';

// Pinned literally (not derived from the constants): the API's table plus "decisions need ready".
const TABLE: [ReviewState, VersionStatus, ReviewAction[]][] = [
  ['in_review', 'ready', ['approve', 'request_changes']],
  ['in_review', 'processing', []],
  ['in_review', 'pending_upload', []],
  ['in_review', 'failed', []],
  ['approved', 'ready', ['reopen']],
  ['approved', 'failed', ['reopen']],
  ['changes_requested', 'ready', ['reopen']],
  ['changes_requested', 'processing', ['reopen']],
];

describe('available review actions', () => {
  it.each(TABLE)('a version %s and %s offers %j', (reviewState, status, expected) => {
    expect(availableActions(aVersion({ review_state: reviewState, status }))).toEqual(expected);
  });
});

describe('review error message', () => {
  it('names the state that won a conflict', () => {
    const error = apiError(409, 'Conflict', 'REVIEW_STATE_CONFLICT');
    error.currentState = 'changes_requested';

    expect(reviewErrorMessage(error, en)).toBe(
      'Someone else decided first: this version is now “Changes requested”. Check it, then decide again. Your note is kept.',
    );
  });

  it('falls back to a plain sentence for a conflict without a known state', () => {
    const error = apiError(409, 'Conflict', 'REVIEW_STATE_CONFLICT');
    error.currentState = 'rejected';

    expect(reviewErrorMessage(error, en)).toBe(en.reviews.errors.transition);
  });

  it.each([
    ['INVALID_REVIEW_NOTE', en.reviews.errors.invalidNote],
    ['VERSION_NOT_READY', en.reviews.errors.notReady],
    ['INVALID_REVIEW_TRANSITION', en.reviews.errors.transition],
    ['INSUFFICIENT_SCOPE', en.reviews.errors.readOnly],
    ['ASSET_VERSION_NOT_FOUND', en.reviews.errors.gone],
    ['IDEMPOTENCY_KEY_REUSED', en.reviews.errors.retry],
  ])('explains %s', (code, message) => {
    expect(reviewErrorMessage(apiError(409, 'x', code), en)).toBe(message);
  });

  it('describes other failures as every other view does', () => {
    expect(reviewErrorMessage(apiError(0, 'Failed to fetch'), en)).toMatch(/reach/i);
    expect(reviewErrorMessage(new Error('boom'), en)).toBeTruthy();
  });
});
