import type { MockInstance } from 'vitest';

import type { Comment, CommentThread } from '@/interfaces/comment.interface';

/** A request the in-memory comments API of the tests saw (`src/test/comment-api.ts`). */
export interface SentRequest {
  method: string;
  path: string;
  body: unknown;
  idempotencyKey: string | null;
}

/** The in-memory comments API the component tests talk to. */
export interface CommentServer {
  fetchMock: MockInstance<typeof fetch>;
  threads: Map<string, CommentThread[]>;
  replies: Map<string, Comment[]>;
  sent: SentRequest[];
  /** Answer the next `method` request to a path prefix with this response instead. */
  failNext: (method: string, pathPrefix: string, response: Response | Error) => void;
  /** Requests whose path starts with `prefix` and use `method`. */
  requests: (method: string, prefix: string) => SentRequest[];
}
