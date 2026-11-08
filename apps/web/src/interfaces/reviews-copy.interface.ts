import type { ReviewAction, ReviewState } from '@/interfaces/review.interface';

/** Copy of review states, decisions and history (KILN-11). */
export interface ReviewsCopy {
  tab: string;
  state: Record<ReviewState, string>;
  versionLabel: string;
  versionOption: (number: number, isNewest: boolean) => string;
  /** "Version 3 is" before the state badge. */
  currentLabel: (number: number) => string;
  formLabel: (number: number) => string;
  noteLabel: string;
  notePlaceholder: string;
  action: Record<ReviewAction, string>;
  saving: string;
  notReadyHint: string;
  decidedHint: string;
  announce: Record<ReviewAction, (number: number) => string>;
  /** Someone else decided first: the state the version is in now. */
  conflict: (state: string) => string;
  errors: {
    invalidNote: string;
    notReady: string;
    readOnly: string;
    transition: string;
    gone: string;
    /** The key of an earlier, different decision came back (should not happen; try again). */
    retry: string;
  };
  historyTitle: string;
  historyLabel: (number: number) => string;
  loading: string;
  loadFailed: string;
  retry: string;
  emptyTitle: string;
  emptyBody: string;
  showOlder: string;
  loadingOlder: string;
  /** "Ada Artist approved". */
  event: Record<ReviewAction, (name: string) => string>;
  /** For screen readers: "from In review to Approved". */
  fromTo: (from: string, to: string) => string;
  filterLabel: string;
  filterAll: string;
  filteredEmptyTitle: (state: string) => string;
  filteredEmptyBody: string;
  showAllStates: string;
}
