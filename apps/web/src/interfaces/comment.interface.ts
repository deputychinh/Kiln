import type { components } from '@/api/kiln.schema';

type Schemas = components['schemas'];

export type CommentThread = Schemas['ThreadOut'];
export type ThreadPage = Schemas['ThreadPageOut'];
export type Comment = Schemas['CommentOut'];
export type CommentPage = Schemas['CommentPageOut'];
export type Region = Schemas['RegionOut'];
export type RegionInput = Schemas['RegionIn'];
export type RegionShape = Schemas['RegionShape'];

/** A region being marked, normalised to the image (0 to 1, origin top left, like the API). */
export interface DraftRegion {
  shape: RegionShape;
  x: number;
  y: number;
  /** 0 for a point. */
  width: number;
  height: number;
}

/** A point on the image, normalised to it. */
export interface ImagePoint {
  x: number;
  y: number;
}

/** What the preview overlay and the comments panel share while someone reviews a version. */
export interface Annotation {
  /** The thread chosen on the image or in the list (its region is highlighted). */
  selectedThreadId: string | null;
  /** Bumped when a choice should move focus to the thread in the list (a region was pressed). */
  focusNonce: number;
  select: (threadId: string | null, options?: { moveFocus?: boolean }) => void;
  /** The region being marked for the next comment. */
  draft: DraftRegion | null;
  setDraft: (draft: DraftRegion | null) => void;
  /** True while the image takes drags and the draft takes arrow keys. */
  isMarking: boolean;
  startMarking: (initial: DraftRegion) => void;
  /** Ends marking; `keep` false drops the draft. Focus goes to the comment field or the button. */
  stopMarking: (keep: boolean) => void;
  /** Callback refs for the comment field and the Mark region button (focus moves between them). */
  setComposer: (element: HTMLTextAreaElement | null) => void;
  setMarkButton: (element: HTMLButtonElement | null) => void;
  focusComposer: () => void;
  focusMarkButton: () => void;
  reset: () => void;
}

export interface StartThreadInput {
  body: string;
  region: RegionInput | null;
  idempotencyKey: string;
}

export interface ReplyInput {
  threadId: string;
  body: string;
  idempotencyKey: string;
}

/** An idempotency key and the content it was made for (the same content keeps the key). */
export interface DraftKey {
  key: string;
  signature: string;
}
