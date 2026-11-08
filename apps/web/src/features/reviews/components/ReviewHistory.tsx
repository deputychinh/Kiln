import { EmptyState, ErrorState, ICON_SIZE, Skeleton } from '@kiln/ui';
import { CircleAlert, CircleCheck, History, RotateCcw } from 'lucide-react';
import type { ReactElement } from 'react';

import { RelativeTime } from '@/components/RelativeTime/RelativeTime';
import { REVIEW_STATE_TONE } from '@/constants/reviews.constant';
import type { useReviewHistory } from '@/features/reviews/hooks/useReviews';
import { useCopy } from '@/hooks/useCopy';
import { describeError } from '@/utils/error.util';

import './ReviewHistory.css';

const ICONS = { approve: CircleCheck, request_changes: CircleAlert, reopen: RotateCcw } as const;

interface ReviewHistoryProps {
  history: ReturnType<typeof useReviewHistory>;
  versionNumber: number;
}

/** A version's decisions as a timeline, newest first, with its four states and older pages. */
export const ReviewHistory = ({ history, versionNumber }: ReviewHistoryProps): ReactElement => {
  const copy = useCopy();
  const events = history.data?.pages.flatMap((page) => page.items) ?? [];

  let body: ReactElement;
  if (history.isPending) {
    body = (
      <div className="review-history__loading" role="status">
        <span className="visually-hidden">{copy.reviews.loading}</span>
        <Skeleton />
        <Skeleton />
      </div>
    );
  } else if (history.isError && events.length === 0) {
    body = (
      <ErrorState
        title={copy.reviews.loadFailed}
        titleAs="p"
        message={describeError(history.error, copy)}
        retryLabel={copy.reviews.retry}
        onRetry={() => void history.refetch()}
        isRetrying={history.isFetching}
      />
    );
  } else if (events.length === 0) {
    body = (
      <EmptyState
        icon={<History aria-hidden="true" />}
        title={copy.reviews.emptyTitle}
        titleAs="h3"
      >
        {copy.reviews.emptyBody}
      </EmptyState>
    );
  } else {
    body = (
      <>
        <ol className="review-history__events">
          {events.map((event) => {
            const Icon = ICONS[event.action];
            return (
              <li
                key={event.id}
                className={`review-history__event review-history__event--${REVIEW_STATE_TONE[event.to_state]}`}
              >
                <span className="review-history__icon" aria-hidden="true">
                  <Icon size={ICON_SIZE.sm} />
                </span>
                <span className="review-history__what">
                  {copy.reviews.event[event.action](event.actor.display_name)}
                  <span className="visually-hidden">
                    {`, ${copy.reviews.fromTo(
                      copy.reviews.state[event.from_state],
                      copy.reviews.state[event.to_state],
                    )}`}
                  </span>
                </span>
                <span className="review-history__when">
                  <RelativeTime iso={event.created_at} />
                </span>
                {event.note ? <p className="review-history__note">{event.note}</p> : null}
              </li>
            );
          })}
        </ol>
        {history.hasNextPage ? (
          <button
            type="button"
            className="review-history__more"
            aria-disabled={history.isFetchingNextPage}
            onClick={() => {
              if (!history.isFetchingNextPage) void history.fetchNextPage();
            }}
          >
            {history.isFetchingNextPage ? copy.reviews.loadingOlder : copy.reviews.showOlder}
          </button>
        ) : null}
        {history.isFetchNextPageError ? (
          <ErrorState
            title={copy.reviews.loadFailed}
            titleAs="p"
            message={describeError(history.error, copy)}
            retryLabel={copy.reviews.retry}
            onRetry={() => void history.fetchNextPage()}
            isRetrying={history.isFetchingNextPage}
          />
        ) : null}
      </>
    );
  }

  return (
    <section className="review-history" aria-label={copy.reviews.historyLabel(versionNumber)}>
      <h3 className="review-history__title">{copy.reviews.historyTitle}</h3>
      {body}
    </section>
  );
};
