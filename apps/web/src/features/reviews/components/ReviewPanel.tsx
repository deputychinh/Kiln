import { Button, ButtonVariant, ICON_SIZE, TextArea } from '@kiln/ui';
import { CircleAlert, CircleCheck, RotateCcw } from 'lucide-react';
import { type ReactElement, useCallback, useId, useRef, useState } from 'react';

import { ReviewBadge } from '@/components/ReviewBadge/ReviewBadge';
import { REVIEW_NOTE_MAX_LENGTH } from '@/constants/reviews.constant';
import { ReviewHistory } from '@/features/reviews/components/ReviewHistory';
import { useReviewHistory, useReviewTransition } from '@/features/reviews/hooks/useReviews';
import { useCopy } from '@/hooks/useCopy';
import type { AssetVersion } from '@/interfaces/asset.interface';
import type { DraftKey } from '@/interfaces/comment.interface';
import type { ReviewAction } from '@/interfaces/review.interface';
import { draftKey } from '@/utils/comment.util';
import { availableActions, reviewErrorMessage } from '@/utils/review.util';

import './ReviewPanel.css';

const ICONS = { approve: CircleCheck, request_changes: CircleAlert, reopen: RotateCcw } as const;

interface ReviewPanelProps {
  assetId: string;
  versions: AssetVersion[];
  version: AssetVersion;
  onVersionChange: (versionId: string) => void;
}

/**
 * The Review tab: the chosen version's state, the decisions the state machine allows now with an
 * optional note, and the history. A decision names the state it was made on; if someone else
 * decided first, the API refuses it and the panel says who won, keeping the note.
 */
export const ReviewPanel = ({
  assetId,
  versions,
  version,
  onVersionChange,
}: ReviewPanelProps): ReactElement => {
  const copy = useCopy();
  const selectId = useId();
  const [note, setNote] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const problemRef = useRef<HTMLParagraphElement>(null);
  const keyRef = useRef<DraftKey | null>(null);
  const [announcements, setAnnouncements] = useState<{ id: number; text: string }[]>([]);
  const announce = useCallback((text: string) => {
    setAnnouncements((current) => [...current.slice(-2), { id: Date.now() + Math.random(), text }]);
  }, []);
  const transition = useReviewTransition(assetId, version.id);
  const history = useReviewHistory(version.id);
  const newest = versions.at(-1);
  const actions = availableActions(version);
  const isDecided = version.review_state !== 'in_review';

  const decide = (action: ReviewAction): void => {
    if (transition.isPending) return;
    const expectedState = version.review_state;
    // The same decision on the same state and note keeps its key: a retry replays, never repeats.
    keyRef.current = draftKey(keyRef.current, JSON.stringify([action, expectedState, note]));
    setProblem(null);
    transition.mutate(
      { action, expectedState, note, idempotencyKey: keyRef.current.key },
      {
        onSuccess: () => {
          setNote('');
          keyRef.current = null;
          announce(copy.reviews.announce[action](version.number));
        },
        onError: (failure) => {
          setProblem(reviewErrorMessage(failure, copy));
          // After the message renders, so a screen reader and the eye land on it.
          requestAnimationFrame(() => problemRef.current?.focus());
        },
      },
    );
  };

  let hint: string | null = null;
  if (actions.length === 0) hint = copy.reviews.notReadyHint;
  else if (isDecided) hint = copy.reviews.decidedHint;

  return (
    <div className="review-panel">
      {versions.length > 1 ? (
        <div className="review-panel__version">
          <label className="review-panel__label" htmlFor={selectId}>
            {copy.reviews.versionLabel}
          </label>
          <select
            id={selectId}
            className="review-panel__select"
            value={version.id}
            onChange={(event) => {
              setProblem(null);
              onVersionChange(event.target.value);
            }}
          >
            {[...versions].reverse().map((option) => (
              <option key={option.id} value={option.id}>
                {copy.reviews.versionOption(option.number, option.id === newest?.id)}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <p className="review-panel__state">
        <span>{copy.reviews.currentLabel(version.number)}</span>
        <ReviewBadge state={version.review_state} />
      </p>
      <form
        className="review-panel__form"
        aria-label={copy.reviews.formLabel(version.number)}
        onSubmit={(event) => event.preventDefault()}
      >
        {actions.length > 0 ? (
          <TextArea
            label={copy.reviews.noteLabel}
            placeholder={copy.reviews.notePlaceholder}
            value={note}
            maxLength={REVIEW_NOTE_MAX_LENGTH}
            showCount
            onChange={(event) => setNote(event.target.value)}
          />
        ) : null}
        {hint ? <p className="review-panel__hint">{hint}</p> : null}
        {problem ? (
          <p ref={problemRef} className="review-panel__problem" role="alert" tabIndex={-1}>
            {problem}
          </p>
        ) : null}
        {actions.length > 0 ? (
          <div className="review-panel__actions">
            {actions.map((action) => {
              const Icon = ICONS[action];
              return (
                <Button
                  key={action}
                  type="button"
                  variant={action === 'approve' ? ButtonVariant.Primary : ButtonVariant.Secondary}
                  icon={<Icon size={ICON_SIZE.sm} />}
                  // aria-disabled, not disabled: the pressed button keeps focus while saving.
                  aria-disabled={transition.isPending}
                  onClick={() => decide(action)}
                >
                  {transition.isPending && transition.variables?.action === action
                    ? copy.reviews.saving
                    : copy.reviews.action[action]}
                </Button>
              );
            })}
          </div>
        ) : null}
      </form>
      <ReviewHistory history={history} versionNumber={version.number} />
      <div className="visually-hidden" role="status" aria-live="polite">
        {announcements.map((item) => (
          <p key={item.id}>{item.text}</p>
        ))}
      </div>
    </div>
  );
};
