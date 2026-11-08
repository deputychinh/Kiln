import { Button, ButtonVariant, ICON_SIZE, TextArea } from '@kiln/ui';
import { CircleAlert, CircleCheck, RotateCcw } from 'lucide-react';
import { type KeyboardEvent, type ReactElement, useEffect, useRef, useState } from 'react';

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

/** A held Enter repeats: once focus has moved to the next action, it must not press that too. */
const ignoreRepeatedEnter = (event: KeyboardEvent<HTMLButtonElement>): void => {
  if (event.key === 'Enter' && event.repeat) event.preventDefault();
};

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
  const hintRef = useRef<HTMLParagraphElement>(null);
  const actionsRef = useRef<HTMLDivElement>(null);
  const keyRef = useRef<DraftKey | null>(null);
  // The revision this form's last decision made: once the page shows it, focus moves (KILN-48,
  // WCAG 2.4.3); `movedForRef` remembers the revision focus already moved for.
  const [decidedRevision, setDecidedRevision] = useState<number | null>(null);
  const movedForRef = useRef<number | null>(null);
  const transition = useReviewTransition(assetId, version.id);
  const actions = availableActions(version);
  const isDecided = version.review_state !== 'in_review';

  // The pressed button unmounts once the new state is shown (Approve → Reopen), so focus goes on
  // purpose to the first action the new state offers, as a toggle button keeps it; with none
  // (a reopened version that is not ready), to the hint that says why. The polite status alone
  // announces the outcome; the focused element adds only its name or the reason, never the state.
  useEffect(() => {
    if (decidedRevision === null || movedForRef.current === decidedRevision) return;
    if (version.review_revision < decidedRevision) return;
    movedForRef.current = decidedRevision;
    const next = actionsRef.current?.querySelector('button');
    (next ?? hintRef.current)?.focus();
  }, [decidedRevision, version.review_revision]);

  // A refusal takes focus once it has rendered (an effect, not a timer that can run before the
  // commit), so a screen reader and the eye land on it. Focus is the one channel: the message is
  // no alert, or it would be read twice (KILN-48).
  useEffect(() => {
    if (problem !== null) problemRef.current?.focus();
  }, [problem]);

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
        onSuccess: (event) => {
          setNote('');
          keyRef.current = null;
          setDecidedRevision(event.sequence);
          announce(copy.reviews.announce[action](version.number));
        },
        onError: (failure) => {
          setProblem(reviewErrorMessage(failure, copy));
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
        {hint ? (
          <p ref={hintRef} className="review-panel__hint" tabIndex={-1}>
            {hint}
          </p>
        ) : null}
        {problem ? (
          <p ref={problemRef} className="review-panel__problem" tabIndex={-1}>
            {problem}
          </p>
        ) : null}
        {actions.length > 0 ? (
          <div ref={actionsRef} className="review-panel__actions">
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
                  onKeyDown={ignoreRepeatedEnter}
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
