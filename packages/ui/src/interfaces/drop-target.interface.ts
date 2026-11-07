import type { ReactNode } from 'react';

/** One place files can be dropped on the `DropOverlay`. */
export interface DropTarget {
  /** Passed back with the dropped files. */
  id: string;
  /** What dropping here does, e.g. "New assets". */
  label: string;
  /** Limits worth knowing before dropping, e.g. the accepted types and size. */
  hint?: string;
  /** A large decorative icon. */
  icon?: ReactNode;
}
