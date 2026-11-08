import { apiError } from '@/api/client';
import { en } from '@/locales/en';
import { commentErrorMessage } from '@/utils/comment-error.util';

describe('commentErrorMessage', () => {
  it.each([
    ['INVALID_COMMENT_BODY', en.comments.errors.invalidBody],
    ['INVALID_REGION', en.comments.errors.invalidRegion],
    ['REGION_NOT_SUPPORTED', en.comments.errors.invalidRegion],
    ['NOT_COMMENT_AUTHOR', en.comments.errors.notAuthor],
    ['COMMENT_DELETED', en.comments.errors.gone],
    ['COMMENT_NOT_FOUND', en.comments.errors.gone],
    ['COMMENT_THREAD_NOT_FOUND', en.comments.errors.gone],
    ['INSUFFICIENT_SCOPE', en.comments.errors.readOnly],
  ])('says what %s means', (code, message) => {
    expect(commentErrorMessage(apiError(422, 'Unprocessable Entity', code), en)).toBe(message);
  });

  it('falls back to the general wording for other failures', () => {
    expect(commentErrorMessage(apiError(0, 'Failed to fetch'), en)).toBe(en.errors.unreachable);
    expect(commentErrorMessage(apiError(500, 'Internal Server Error', 'INTERNAL'), en)).toBe(
      'Internal Server Error',
    );
  });
});
