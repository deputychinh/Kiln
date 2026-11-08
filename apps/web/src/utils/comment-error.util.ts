import { isApiError } from '@/api/client';
import type { Copy } from '@/interfaces/copy.interface';
import { describeError } from '@/utils/error.util';

/** The sentence for a failed comment action: the API's code when it says more than its title. */
export const commentErrorMessage = (error: unknown, copy: Copy): string => {
  const { errors } = copy.comments;
  const byCode: Record<string, string> = {
    INVALID_COMMENT_BODY: errors.invalidBody,
    INVALID_REGION: errors.invalidRegion,
    REGION_NOT_SUPPORTED: errors.invalidRegion,
    NOT_COMMENT_AUTHOR: errors.notAuthor,
    COMMENT_DELETED: errors.gone,
    COMMENT_NOT_FOUND: errors.gone,
    COMMENT_THREAD_NOT_FOUND: errors.gone,
    INSUFFICIENT_SCOPE: errors.readOnly,
  };
  const known = isApiError(error) && error.code !== null ? byCode[error.code] : undefined;
  return known ?? describeError(error, copy);
};
