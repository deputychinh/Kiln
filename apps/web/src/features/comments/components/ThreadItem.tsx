import { Badge, BadgeTone, Button, ButtonVariant, ICON_SIZE, TextArea } from '@kiln/ui';
import { Check, ChevronDown, ChevronUp, MessageSquare, RotateCcw } from 'lucide-react';
import { type ReactElement, useEffect, useId, useRef, useState } from 'react';

import { COMMENT_BODY_MAX_LENGTH } from '@/constants/comments.constant';
import { CommentEntry } from '@/features/comments/components/CommentEntry';
import { regionMarkId } from '@/features/comments/components/RegionOverlay';
import { useReplies, useReply, useResolve } from '@/features/comments/hooks/useComments';
import { useCopy } from '@/hooks/useCopy';
import type { Annotation, CommentThread, DraftKey } from '@/interfaces/comment.interface';
import { commentErrorMessage } from '@/utils/comment-error.util';
import { draftKey } from '@/utils/comment.util';
import { describeError } from '@/utils/error.util';

import './ThreadItem.css';

interface ThreadItemProps {
  thread: CommentThread;
  versionId: string;
  meId: string | undefined;
  annotation: Annotation;
  announce: (message: string) => void;
  /** Called after this thread was resolved, in case the list now hides it (focus must not drop). */
  onResolved: () => void;
}

/** One thread: its number and region, the first comment, replies on demand, reply and resolve. */
export const ThreadItem = ({
  thread,
  versionId,
  meId,
  annotation,
  announce,
  onResolved,
}: ThreadItemProps): ReactElement => {
  const copy = useCopy();
  const repliesId = useId();
  const articleRef = useRef<HTMLElement>(null);
  const replyButtonRef = useRef<HTMLButtonElement>(null);
  const replyFieldRef = useRef<HTMLTextAreaElement>(null);
  const keyRef = useRef<DraftKey | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [isReplying, setIsReplying] = useState(false);
  const [reply, setReply] = useState('');
  const [replyError, setReplyError] = useState<string | undefined>();
  const replies = useReplies(thread.id, isOpen);
  const postReply = useReply(versionId);
  const resolve = useResolve(versionId);
  const isSelected = annotation.selectedThreadId === thread.id;
  const isResolved = thread.resolved_at !== null;
  const { focusNonce } = annotation;

  // A region pressed on the image brings its thread into view and gives it focus.
  useEffect(() => {
    if (focusNonce === 0 || !isSelected) return;
    // `start` honours the scroll margin, so the thread stops below a pinned preview.
    articleRef.current?.scrollIntoView?.({ block: 'start' });
    articleRef.current?.focus({ preventScroll: true });
  }, [focusNonce, isSelected]);
  // Into the reply field when it opens; back to Reply once it has closed (and Reply exists again).
  const hasOpenedReplyRef = useRef(false);
  useEffect(() => {
    if (isReplying) {
      hasOpenedReplyRef.current = true;
      replyFieldRef.current?.focus();
    } else if (hasOpenedReplyRef.current) {
      replyButtonRef.current?.focus();
    }
  }, [isReplying]);

  // A deleted comment keeps its place but loses its buttons: the thread, named by its number and
  // author, is the stable place for focus; the polite status says "Comment deleted" once.
  const focusThread = (): void => articleRef.current?.focus();
  const closeReply = (): void => {
    setIsReplying(false);
    setReply('');
    setReplyError(undefined);
  };
  const sendReply = (): void => {
    if (postReply.isPending) return;
    if (!reply.trim()) {
      setReplyError(copy.comments.bodyRequired);
      replyFieldRef.current?.focus();
      return;
    }
    keyRef.current = draftKey(keyRef.current, reply);
    postReply.mutate(
      { threadId: thread.id, body: reply, idempotencyKey: keyRef.current.key },
      {
        onSuccess: () => {
          keyRef.current = null;
          setIsOpen(true);
          announce(copy.comments.announce.replied);
          closeReply();
        },
        onError: (failure) => {
          // The field describes its error: focusing it is the one way it is read (KILN-48).
          setReplyError(commentErrorMessage(failure, copy));
          replyFieldRef.current?.focus();
        },
      },
    );
  };

  const loadedReplies = replies.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <li className="thread-item">
      <article
        ref={articleRef}
        tabIndex={-1}
        className={[
          'thread-item__card',
          isSelected ? 'thread-item__card--selected' : '',
          isResolved ? 'thread-item__card--resolved' : '',
        ].join(' ')}
        aria-label={copy.comments.threadLabel(thread.number, thread.comment.author.display_name)}
      >
        <div className="thread-item__head">
          {thread.region ? (
            <button
              type="button"
              className="thread-item__number"
              aria-label={copy.comments.showOnImage(thread.number)}
              aria-pressed={isSelected}
              onClick={() => {
                annotation.select(isSelected ? null : thread.id);
                document.getElementById(regionMarkId(thread.id))?.scrollIntoView?.({
                  block: 'nearest',
                });
              }}
            >
              {thread.number}
            </button>
          ) : (
            <span
              className="thread-item__number thread-item__number--plain"
              title={copy.comments.wholeImage}
            >
              <MessageSquare size={ICON_SIZE.sm} aria-hidden="true" />
              <span className="visually-hidden">{copy.comments.wholeImage}</span>
            </span>
          )}
          {isResolved ? (
            <Badge tone={BadgeTone.Success} icon={<Check size={ICON_SIZE.sm} />}>
              {thread.resolved_by
                ? copy.comments.resolvedBy(thread.resolved_by.display_name)
                : copy.comments.resolved}
            </Badge>
          ) : null}
        </div>
        <CommentEntry
          comment={thread.comment}
          versionId={versionId}
          isOwn={thread.comment.author.id === meId}
          announce={announce}
          onDeleted={focusThread}
        />
        {thread.reply_count > 0 ? (
          <button
            type="button"
            className="thread-item__toggle"
            aria-expanded={isOpen}
            aria-controls={repliesId}
            onClick={() => setIsOpen((open) => !open)}
          >
            {isOpen ? (
              <ChevronUp size={ICON_SIZE.sm} aria-hidden="true" />
            ) : (
              <ChevronDown size={ICON_SIZE.sm} aria-hidden="true" />
            )}
            {isOpen ? copy.comments.hideReplies : copy.comments.showReplies(thread.reply_count)}
          </button>
        ) : null}
        <div id={repliesId} hidden={!isOpen || thread.reply_count === 0}>
          {replies.isPending && isOpen ? (
            <p className="thread-item__note" role="status">
              {copy.comments.loading}
            </p>
          ) : null}
          {replies.isError ? (
            <p className="thread-item__error" role="alert">
              {describeError(replies.error, copy)}{' '}
              <button
                type="button"
                className="thread-item__link"
                onClick={() => void replies.refetch()}
              >
                {copy.comments.retry}
              </button>
            </p>
          ) : null}
          {loadedReplies.length > 0 ? (
            <ol
              className="thread-item__replies"
              aria-label={copy.comments.repliesLabel(thread.number)}
            >
              {loadedReplies.map((comment) => (
                <li key={comment.id} className="thread-item__reply">
                  <CommentEntry
                    comment={comment}
                    versionId={versionId}
                    isOwn={comment.author.id === meId}
                    announce={announce}
                    onDeleted={focusThread}
                  />
                </li>
              ))}
            </ol>
          ) : null}
          {replies.hasNextPage ? (
            <button
              type="button"
              className="thread-item__link"
              aria-disabled={replies.isFetchingNextPage}
              onClick={() => {
                if (!replies.isFetchingNextPage) void replies.fetchNextPage();
              }}
            >
              {copy.comments.showMoreReplies}
            </button>
          ) : null}
        </div>
        {isReplying ? (
          <form
            className="thread-item__reply-form"
            onSubmit={(event) => {
              event.preventDefault();
              sendReply();
            }}
          >
            <TextArea
              ref={replyFieldRef}
              label={copy.comments.replyLabel(thread.number)}
              isLabelHidden
              value={reply}
              maxLength={COMMENT_BODY_MAX_LENGTH}
              showCount
              error={replyError}
              onChange={(event) => {
                setReply(event.target.value);
                setReplyError(undefined);
              }}
              onKeyDown={(event) => {
                if (event.key === 'Escape') closeReply();
              }}
            />
            <div className="thread-item__actions">
              <Button
                type="submit"
                variant={ButtonVariant.Primary}
                aria-disabled={postReply.isPending}
              >
                {postReply.isPending ? copy.comments.posting : copy.comments.postReply}
              </Button>
              <Button type="button" variant={ButtonVariant.Ghost} onClick={closeReply}>
                {copy.comments.cancel}
              </Button>
            </div>
          </form>
        ) : (
          <div className="thread-item__actions">
            <Button
              ref={replyButtonRef}
              type="button"
              variant={ButtonVariant.Ghost}
              aria-label={copy.comments.replyLabel(thread.number)}
              onClick={() => setIsReplying(true)}
            >
              {copy.comments.reply}
            </Button>
            <Button
              type="button"
              variant={ButtonVariant.Ghost}
              icon={isResolved ? <RotateCcw size={ICON_SIZE.sm} /> : <Check size={ICON_SIZE.sm} />}
              aria-disabled={resolve.isPending}
              onClick={() => {
                if (resolve.isPending) return;
                resolve.mutate(
                  { threadId: thread.id, resolved: !isResolved },
                  {
                    onSuccess: () => {
                      if (isResolved) {
                        announce(copy.comments.announce.reopened(thread.number));
                        return;
                      }
                      announce(copy.comments.announce.resolved(thread.number));
                      onResolved();
                    },
                    onError: (failure) => announce(commentErrorMessage(failure, copy)),
                  },
                );
              }}
            >
              {isResolved ? copy.comments.reopen : copy.comments.resolve}
            </Button>
          </div>
        )}
      </article>
    </li>
  );
};
