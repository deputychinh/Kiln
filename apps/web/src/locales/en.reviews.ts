import type { ReviewsCopy } from '@/interfaces/reviews-copy.interface';

/** English copy of review states, decisions and history (KILN-11). */
export const enReviews: ReviewsCopy = {
  tab: 'Review',
  state: { in_review: 'In review', approved: 'Approved', changes_requested: 'Changes requested' },
  versionLabel: 'Review of',
  versionOption: (number, isNewest) =>
    isNewest ? `Version ${String(number)} (newest)` : `Version ${String(number)}`,
  currentLabel: (number) => `Version ${String(number)} is`,
  formLabel: (number) => `Decide on version ${String(number)}`,
  noteLabel: 'Note (optional)',
  notePlaceholder: 'Why? The artist sees this in the history.',
  action: { approve: 'Approve', request_changes: 'Request changes', reopen: 'Reopen' },
  saving: 'Saving…',
  notReadyHint: 'This version can be approved or sent back once it has finished processing.',
  decidedHint: 'Reopen it to put it back in review and decide again.',
  announce: {
    approve: (number) => `Version ${String(number)} approved`,
    request_changes: (number) => `Changes requested on version ${String(number)}`,
    reopen: (number) => `Version ${String(number)} is back in review`,
  },
  conflict: (state) =>
    `Someone else decided first: this version is now “${state}”. Check it, then decide again. Your note is kept.`,
  errors: {
    invalidNote:
      'The note is too long or has hidden characters. Keep it to 1,000 characters of plain text.',
    notReady: 'This version is not ready to be reviewed (it is still processing or failed).',
    readOnly: 'Your access is read-only, so you cannot review.',
    transition: 'That decision no longer applies to this version. Check its state and try again.',
    gone: 'This version no longer exists.',
  },
  historyTitle: 'History',
  historyLabel: (number) => `Review history of version ${String(number)}`,
  loading: 'Loading the review history…',
  loadFailed: 'The review history did not load',
  retry: 'Try again',
  emptyTitle: 'No decisions yet',
  emptyBody: 'Approve this version or request changes, and each decision is listed here.',
  showOlder: 'Show older',
  loadingOlder: 'Loading older…',
  event: {
    approve: (name) => `${name} approved`,
    request_changes: (name) => `${name} requested changes`,
    reopen: (name) => `${name} reopened`,
  },
  fromTo: (from, to) => `from ${from} to ${to}`,
  filterLabel: 'Review state',
  filterAll: 'All states',
  filteredEmptyTitle: (state) => `No assets loaded are “${state}”`,
  filteredEmptyBody: 'None of the assets loaded so far is in this state. Load more, or show all.',
  showAllStates: 'Show all states',
};
