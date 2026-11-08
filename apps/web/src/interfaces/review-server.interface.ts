import type { MockInstance } from 'vitest';

import type { SentRequest } from '@/interfaces/comment-server.interface';
import type { ReviewAction } from '@/interfaces/review.interface';

/** The in-memory reviews API the component tests talk to (`src/test/review-api.ts`). */
export interface ReviewServer {
  fetchMock: MockInstance<typeof fetch>;
  sent: SentRequest[];
  /** Another reviewer decides on a version, as if in another browser. */
  decideAsSomeoneElse: (versionId: string, action: ReviewAction) => void;
  failNext: (method: string, prefix: string, response: Response | Error) => void;
  requests: (method: string, prefix: string) => SentRequest[];
}
