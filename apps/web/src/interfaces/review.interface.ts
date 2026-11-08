import type { components } from '@/api/kiln.schema';

type Schemas = components['schemas'];

export type ReviewState = Schemas['ReviewState'];
export type ReviewAction = Schemas['ReviewAction'];
export type ReviewEvent = Schemas['ReviewEventOut'];
export type ReviewEventPage = Schemas['ReviewEventPageOut'];

/** One decision as the Review tab sends it; the key makes a retry replay, never act twice. */
export interface TransitionInput {
  action: ReviewAction;
  /** The state the reviewer saw: the API refuses the decision if it changed since (409). */
  expectedState: ReviewState;
  /** The revision the reviewer saw: also refuses approve → reopen → approve (ADR 0016). */
  expectedRevision: number;
  note: string;
  idempotencyKey: string;
}
