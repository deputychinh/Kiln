import { Button, ButtonVariant, ICON_SIZE, TextArea } from '@kiln/ui';
import { MapPin, SquareDashed, X } from 'lucide-react';
import { type ReactElement, useRef, useState } from 'react';

import { COMMENT_BODY_MAX_LENGTH, REGION_START } from '@/constants/comments.constant';
import { useStartThread } from '@/features/comments/hooks/useComments';
import { useCopy } from '@/hooks/useCopy';
import { useFocusAfterCommit } from '@/hooks/useFocusAfterCommit';
import type { Annotation, DraftKey } from '@/interfaces/comment.interface';
import { commentErrorMessage } from '@/utils/comment-error.util';
import { draftKey } from '@/utils/comment.util';
import { toRegionInput } from '@/utils/region.util';

import './CommentComposer.css';

interface CommentComposerProps {
  versionId: string;
  annotation: Annotation;
  /** Regions can be marked (an image whose preview is shown); otherwise why not, if anything. */
  canMark: boolean;
  markHint: string | null;
  announce: (message: string) => void;
}

/** The new-comment form: text, an optional region marked on the image, and Post. */
export const CommentComposer = ({
  versionId,
  annotation,
  canMark,
  markHint,
  announce,
}: CommentComposerProps): ReactElement => {
  const copy = useCopy();
  const [body, setBody] = useState('');
  const [error, setError] = useState<string | undefined>();
  const start = useStartThread(versionId);
  const keyRef = useRef<DraftKey | null>(null);
  const { draft, isMarking, setComposer, setMarkButton } = annotation;
  // The field describes its error once it is in the DOM; focus it then, so it is read (KILN-48).
  const focusComposerAfterError = useFocusAfterCommit(annotation.focusComposer);

  const submit = (): void => {
    if (start.isPending) return;
    if (!body.trim()) {
      setError(copy.comments.bodyRequired);
      focusComposerAfterError();
      return;
    }
    const region = draft && canMark ? toRegionInput(draft) : null;
    keyRef.current = draftKey(keyRef.current, JSON.stringify([body, region]));
    start.mutate(
      { body, region, idempotencyKey: keyRef.current.key },
      {
        onSuccess: (thread) => {
          setBody('');
          annotation.setDraft(null);
          keyRef.current = null;
          announce(copy.comments.announce.posted(thread.number));
        },
        onError: (failure) => {
          setError(commentErrorMessage(failure, copy));
          focusComposerAfterError();
        },
      },
    );
  };

  return (
    <form
      className="comment-composer"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <TextArea
        ref={setComposer}
        label={copy.comments.composerLabel}
        placeholder={copy.comments.composerPlaceholder}
        value={body}
        maxLength={COMMENT_BODY_MAX_LENGTH}
        showCount
        error={error}
        onChange={(event) => {
          setBody(event.target.value);
          setError(undefined);
        }}
      />
      {isMarking ? <p className="comment-composer__hint">{copy.comments.markingHint}</p> : null}
      {draft && canMark && !isMarking ? (
        <p className="comment-composer__region">
          {draft.shape === 'point' ? (
            <MapPin size={ICON_SIZE.sm} aria-hidden="true" />
          ) : (
            <SquareDashed size={ICON_SIZE.sm} aria-hidden="true" />
          )}
          <span>{copy.comments.regionMarked[draft.shape]}</span>
          <button
            type="button"
            className="comment-composer__remove"
            aria-label={copy.comments.removeRegion}
            title={copy.comments.removeRegion}
            onClick={() => {
              annotation.setDraft(null);
              annotation.focusMarkButton();
            }}
          >
            <X size={ICON_SIZE.sm} aria-hidden="true" />
          </button>
        </p>
      ) : null}
      {markHint ? <p className="comment-composer__hint">{markHint}</p> : null}
      <div className="comment-composer__actions">
        {canMark ? (
          <Button
            ref={setMarkButton}
            type="button"
            variant={ButtonVariant.Secondary}
            icon={<SquareDashed size={ICON_SIZE.sm} />}
            aria-pressed={isMarking}
            onClick={() => {
              if (isMarking) {
                annotation.stopMarking(draft !== null);
                return;
              }
              annotation.startMarking({ ...REGION_START });
            }}
          >
            {draft && !isMarking ? copy.comments.markAgain : copy.comments.markRegion}
          </Button>
        ) : null}
        <Button type="submit" variant={ButtonVariant.Primary} aria-disabled={start.isPending}>
          {start.isPending ? copy.comments.posting : copy.comments.post}
        </Button>
      </div>
    </form>
  );
};
