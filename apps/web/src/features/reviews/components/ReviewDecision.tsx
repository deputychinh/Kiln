import { Button, ButtonVariant, ICON_SIZE, TextArea } from '@kiln/ui';
import { CircleAlert, CircleCheck, RotateCcw } from 'lucide-react';
import { type ReactElement, useRef, useState } from 'react';

import { ReviewBadge } from '@/components/ReviewBadge/ReviewBadge';
import { REVIEW_NOTE_MAX_LENGTH } from '@/constants/reviews.constant';
import { useReviewTransition } from '@/features/reviews/hooks/useReviews';
import { useCopy } from '@/hooks/useCopy';
import type { AssetVersion } from '@/interfaces/asset.interface';
import type { DraftKey } from '@/interfaces/comment.interface';
import type { ReviewAction } from '@/interfaces/review.interface';
import { draftKey } from '@/utils/comment.util';
import { availableActions, reviewErrorMessage } from '@/utils/review.util';

const ICONS = { approve: CircleCheck, request_changes: CircleAlert, reopen: RotateCcw } as const;

interface ReviewDecisionProps {
  assetId: string;
  version: AssetVersion;
  announce: (message: string) => void;
}

/**
 * One version's state and the decisions it allows, with an optional note. The parent keys it by
 * version, so the note, a refusal and the idempotency key never carry over to another version.
 */
export const ReviewDecision = ({
  assetId,
  version,
  announce,
}: ReviewDecisionProps): ReactElement => {
  const copy = useCopy();
  const [note, setNote] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const problemRef = useRef<HTMLParagraphElement>(null);
  const keyRef = useRef<DraftKey | null>(null);
  const transition = useReviewTransition(assetId, version.id);
  const actions = availableActions(version);
  const isDecided = version.review_state !== 'in_review';

  const decide = (action: ReviewAction): void => {
    if (transition.isPending) return;
    const expectedState = version.review_state;
    const expectedRevision = version.review_revision;
    // The same decision on the same version, revision and note keeps its key: a retry replays,
    // never repeats; anything else gets a new key (ADR 0016).
    keyRef.current = draftKey(
      keyRef.current,
      JSON.stringify([version.id, expectedRevision, action, expectedState, note]),
    );
    setProblem(null);
    transition.mutate(
      { action, expectedState, expectedRevision, note, idempotencyKey: keyRef.current.key },
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
    <>
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
    </>
  );
};
