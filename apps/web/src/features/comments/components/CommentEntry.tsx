import { Button, ButtonVariant, TextArea } from '@kiln/ui';
import { type ReactElement, useEffect, useRef, useState } from 'react';

import { RelativeTime } from '@/components/RelativeTime/RelativeTime';
import { COMMENT_BODY_MAX_LENGTH } from '@/constants/comments.constant';
import { useDeleteComment, useEditComment } from '@/features/comments/hooks/useComments';
import { useCopy } from '@/hooks/useCopy';
import type { Comment } from '@/interfaces/comment.interface';
import { commentErrorMessage } from '@/utils/comment-error.util';

import './CommentEntry.css';

interface CommentEntryProps {
  comment: Comment;
  versionId: string;
  /** The signed-in person wrote it: Edit and Delete are offered. */
  isOwn: boolean;
  /** Says what happened, in the panel's status region. */
  announce: (message: string) => void;
  /** Called once this comment is deleted: its buttons are gone, so focus must move on purpose. */
  onDeleted: () => void;
}

type Mode = 'view' | 'edit' | 'confirm-delete';

/** One comment: author, time, text; its author edits it in place or deletes it after confirming. */
export const CommentEntry = ({
  comment,
  versionId,
  isOwn,
  announce,
  onDeleted,
}: CommentEntryProps): ReactElement => {
  const copy = useCopy();
  const [mode, setMode] = useState<Mode>('view');
  const [text, setText] = useState(comment.body);
  const [error, setError] = useState<string | undefined>();
  const edit = useEditComment(versionId);
  const remove = useDeleteComment(versionId);
  const editRef = useRef<HTMLTextAreaElement>(null);
  const editButtonRef = useRef<HTMLButtonElement>(null);
  const deleteButtonRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  // Where focus goes back once the inline form has closed (the button exists only then).
  const returnFocusRef = useRef<'edit' | 'delete' | null>(null);

  // Focus follows the inline forms: into the field or onto "Delete comment", and back after.
  useEffect(() => {
    if (mode === 'edit') editRef.current?.focus();
    else if (mode === 'confirm-delete') confirmRef.current?.focus();
    else if (returnFocusRef.current === 'edit') editButtonRef.current?.focus();
    else if (returnFocusRef.current === 'delete') deleteButtonRef.current?.focus();
    returnFocusRef.current = null;
  }, [mode]);

  const close = (returnTo: 'edit' | 'delete'): void => {
    returnFocusRef.current = returnTo;
    setError(undefined);
    setMode('view');
  };
  const save = (): void => {
    if (edit.isPending) return;
    if (!text.trim()) {
      setError(copy.comments.bodyRequired);
      editRef.current?.focus();
      return;
    }
    edit.mutate(
      { comment, body: text },
      {
        onSuccess: () => {
          announce(copy.comments.announce.saved);
          close('edit');
        },
        onError: (failure) => {
          // The field describes its error: focusing it is the one way it is read (KILN-48).
          setError(commentErrorMessage(failure, copy));
          editRef.current?.focus();
        },
      },
    );
  };
  const confirmDelete = (): void => {
    remove.mutate(comment, {
      onSuccess: () => {
        announce(copy.comments.announce.deleted);
        setMode('view');
        // "Delete comment" and the author's buttons unmount (KILN-48, WCAG 2.4.3).
        onDeleted();
      },
      onError: (failure) => setError(commentErrorMessage(failure, copy)),
    });
  };

  return (
    <div className="comment-entry">
      <p className="comment-entry__meta">
        <span className="comment-entry__author">{comment.author.display_name}</span>
        <span className="comment-entry__time">
          <RelativeTime iso={comment.created_at} />
          {comment.edited_at && !comment.deleted ? ` · ${copy.comments.edited}` : null}
        </span>
      </p>
      {mode === 'edit' ? (
        <form
          className="comment-entry__form"
          onSubmit={(event) => {
            event.preventDefault();
            save();
          }}
        >
          <TextArea
            ref={editRef}
            label={copy.comments.editLabel}
            isLabelHidden
            value={text}
            maxLength={COMMENT_BODY_MAX_LENGTH}
            showCount
            error={error}
            onChange={(event) => {
              setText(event.target.value);
              setError(undefined);
            }}
            onKeyDown={(event) => {
              if (event.key === 'Escape') close('edit');
            }}
          />
          <div className="comment-entry__actions">
            <Button type="submit" variant={ButtonVariant.Primary} aria-disabled={edit.isPending}>
              {edit.isPending ? copy.comments.saving : copy.comments.save}
            </Button>
            <Button type="button" variant={ButtonVariant.Ghost} onClick={() => close('edit')}>
              {copy.comments.cancel}
            </Button>
          </div>
        </form>
      ) : (
        <p
          className={`comment-entry__body${comment.deleted ? ' comment-entry__body--deleted' : ''}`}
        >
          {comment.deleted ? copy.comments.deleted : comment.body}
        </p>
      )}
      {mode === 'confirm-delete' ? (
        <div className="comment-entry__confirm">
          <p className="comment-entry__confirm-text">{copy.comments.confirmDelete}</p>
          <div className="comment-entry__actions">
            <Button
              ref={confirmRef}
              variant={ButtonVariant.Secondary}
              className="comment-entry__danger"
              aria-disabled={remove.isPending}
              onClick={() => {
                if (!remove.isPending) confirmDelete();
              }}
              onKeyDown={(event) => {
                if (event.key === 'Escape') close('delete');
              }}
            >
              {remove.isPending ? copy.comments.deleting : copy.comments.confirmDeleteAction}
            </Button>
            <Button
              variant={ButtonVariant.Ghost}
              onClick={() => close('delete')}
              onKeyDown={(event) => {
                if (event.key === 'Escape') close('delete');
              }}
            >
              {copy.comments.cancel}
            </Button>
          </div>
          {error ? (
            <p className="comment-entry__error" role="alert">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
      {isOwn && !comment.deleted && mode === 'view' ? (
        <div className="comment-entry__own">
          <button
            ref={editButtonRef}
            type="button"
            className="comment-entry__link"
            onClick={() => {
              setText(comment.body);
              setMode('edit');
            }}
          >
            {copy.comments.edit}
          </button>
          <button
            ref={deleteButtonRef}
            type="button"
            className="comment-entry__link"
            onClick={() => setMode('confirm-delete')}
          >
            {copy.comments.delete}
          </button>
        </div>
      ) : null}
    </div>
  );
};
