import { EmptyState, ErrorState, Skeleton } from '@kiln/ui';
import { MessageSquare } from 'lucide-react';
import { type ReactElement, useCallback, useId, useRef, useState } from 'react';

import { useMe } from '@/features/auth/hooks/useAuth';
import { CommentComposer } from '@/features/comments/components/CommentComposer';
import { ThreadItem } from '@/features/comments/components/ThreadItem';
import type { useThreads } from '@/features/comments/hooks/useComments';
import { useCopy } from '@/hooks/useCopy';
import type { AssetVersion } from '@/interfaces/asset.interface';
import type { Annotation, CommentThread } from '@/interfaces/comment.interface';
import { describeError } from '@/utils/error.util';

import './CommentsPanel.css';

interface CommentsPanelProps {
  versions: AssetVersion[];
  version: AssetVersion;
  onVersionChange: (versionId: string) => void;
  threads: ReturnType<typeof useThreads>;
  showResolved: boolean;
  onShowResolvedChange: (show: boolean) => void;
  annotation: Annotation;
  canMark: boolean;
  markHint: string | null;
}

/** Splits loaded threads into what the list shows and how many resolved ones it hides. */
export const visibleThreads = (
  threads: CommentThread[],
  showResolved: boolean,
): { shown: CommentThread[]; resolvedCount: number } => {
  const resolvedCount = threads.filter((thread) => thread.resolved_at !== null).length;
  return {
    shown: showResolved ? threads : threads.filter((thread) => thread.resolved_at === null),
    resolvedCount,
  };
};

/** A version's comment threads: pick the version, write a comment, read and answer threads. */
export const CommentsPanel = ({
  versions,
  version,
  onVersionChange,
  threads,
  showResolved,
  onShowResolvedChange,
  annotation,
  canMark,
  markHint,
}: CommentsPanelProps): ReactElement => {
  const copy = useCopy();
  const me = useMe();
  const selectId = useId();
  const listRef = useRef<HTMLDivElement>(null);
  // Outcomes are queued, not replaced, so two quick actions are both announced.
  const [announcements, setAnnouncements] = useState<{ id: number; text: string }[]>([]);
  const announce = useCallback((text: string) => {
    setAnnouncements((current) => [...current.slice(-2), { id: Date.now() + Math.random(), text }]);
  }, []);
  const newest = versions.at(-1);
  const loaded = threads.data?.pages.flatMap((page) => page.items) ?? [];
  const { shown, resolvedCount } = visibleThreads(loaded, showResolved);

  let list: ReactElement;
  if (threads.isPending) {
    list = (
      <div className="comments-panel__loading" role="status">
        <span className="visually-hidden">{copy.comments.loading}</span>
        <Skeleton />
        <Skeleton />
        <Skeleton />
      </div>
    );
  } else if (threads.isError) {
    list = (
      <ErrorState
        title={copy.comments.loadFailed}
        titleAs="p"
        message={describeError(threads.error, copy)}
        retryLabel={copy.comments.retry}
        onRetry={() => void threads.refetch()}
        isRetrying={threads.isFetching}
      />
    );
  } else if (loaded.length === 0) {
    list = (
      <EmptyState
        icon={<MessageSquare aria-hidden="true" />}
        title={copy.comments.emptyTitle}
        titleAs="h3"
      >
        {copy.comments.emptyBody}
      </EmptyState>
    );
  } else {
    list = (
      <>
        {shown.length === 0 ? (
          <p className="comments-panel__note">{copy.comments.allResolved}</p>
        ) : (
          <ol className="comments-panel__threads">
            {shown.map((thread) => (
              <ThreadItem
                key={thread.id}
                thread={thread}
                versionId={version.id}
                meId={me.data?.id}
                annotation={annotation}
                announce={announce}
                onResolved={() => {
                  if (!showResolved) listRef.current?.focus();
                }}
              />
            ))}
          </ol>
        )}
        {threads.hasNextPage ? (
          <button
            type="button"
            className="comments-panel__more"
            aria-disabled={threads.isFetchingNextPage}
            onClick={() => {
              if (!threads.isFetchingNextPage) void threads.fetchNextPage();
            }}
          >
            {threads.isFetchingNextPage ? copy.comments.loadingMore : copy.comments.showMore}
          </button>
        ) : null}
      </>
    );
  }

  return (
    <div className="comments-panel">
      {versions.length > 1 ? (
        <div className="comments-panel__version">
          <label className="comments-panel__label" htmlFor={selectId}>
            {copy.comments.versionLabel}
          </label>
          <select
            id={selectId}
            className="comments-panel__select"
            value={version.id}
            onChange={(event) => onVersionChange(event.target.value)}
          >
            {[...versions].reverse().map((option) => (
              <option key={option.id} value={option.id}>
                {copy.comments.versionOption(option.number, option.id === newest?.id)}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <CommentComposer
        key={version.id}
        versionId={version.id}
        annotation={annotation}
        canMark={canMark}
        markHint={markHint}
        announce={announce}
      />
      {resolvedCount > 0 ? (
        <label className="comments-panel__filter">
          <input
            type="checkbox"
            className="comments-panel__checkbox"
            checked={showResolved}
            onChange={(event) => onShowResolvedChange(event.target.checked)}
          />
          {copy.comments.showResolved(resolvedCount)}
        </label>
      ) : null}
      <div
        ref={listRef}
        className="comments-panel__list"
        role="region"
        aria-label={copy.comments.listLabel(version.number)}
        tabIndex={-1}
      >
        {list}
      </div>
      <div className="visually-hidden" role="status" aria-live="polite">
        {announcements.map((item) => (
          <p key={item.id}>{item.text}</p>
        ))}
      </div>
    </div>
  );
};
