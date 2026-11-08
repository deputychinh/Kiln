import {
  type KeyboardEvent,
  type PointerEvent,
  type ReactElement,
  useEffect,
  useId,
  useRef,
} from 'react';

import { REGION_LABEL_EXCERPT } from '@/constants/comments.constant';
import { useCopy } from '@/hooks/useCopy';
import type {
  Annotation,
  CommentThread,
  DraftRegion,
  ImagePoint,
} from '@/interfaces/comment.interface';
import type { Copy } from '@/interfaces/copy.interface';
import {
  excerpt,
  pointIn,
  regionAfterKey,
  regionFromDrag,
  regionPercents,
  regionStyle,
  toDraft,
} from '@/utils/region.util';

import './RegionOverlay.css';

interface RegionOverlayProps {
  /** The threads shown in the list that mark a region (resolved ones only when shown). */
  threads: CommentThread[];
  annotation: Annotation;
}

/** The DOM id of a thread's mark on the image, so the list can bring it into view. */
export const regionMarkId = (threadId: string): string => `region-${threadId}`;

/** "Region 2: The rim is too bright…": the number and the start of its first comment. */
export const regionLabel = (thread: CommentThread, copy: Copy): string => {
  const text = thread.comment.deleted ? copy.comments.deleted : thread.comment.body;
  return copy.comments.regionButton(thread.number, excerpt(text, REGION_LABEL_EXCERPT));
};

const RegionMark = ({
  thread,
  annotation,
}: {
  thread: CommentThread;
  annotation: Annotation;
}): ReactElement | null => {
  const copy = useCopy();
  if (!thread.region) return null;
  const region = toDraft(thread.region);
  const isSelected = annotation.selectedThreadId === thread.id;
  const label = regionLabel(thread, copy);
  const onPress = (): void => annotation.select(thread.id, { moveFocus: true });
  const block = region.shape === 'point' ? 'region-overlay__pin' : 'region-overlay__rect';
  const className = [
    block,
    isSelected ? `${block}--selected` : '',
    thread.resolved_at ? `${block}--resolved` : '',
  ]
    .join(' ')
    .trim();
  if (region.shape === 'point') {
    return (
      <button
        type="button"
        id={regionMarkId(thread.id)}
        className={className}
        style={regionStyle(region)}
        aria-label={label}
        aria-current={isSelected ? 'true' : undefined}
        onClick={onPress}
      >
        {thread.number}
      </button>
    );
  }
  return (
    <div id={regionMarkId(thread.id)} className={className} style={regionStyle(region)}>
      <span className="region-overlay__box" aria-hidden="true" />
      <button
        type="button"
        className="region-overlay__badge"
        aria-label={label}
        aria-current={isSelected ? 'true' : undefined}
        onClick={onPress}
        title={copy.comments.showOnImage(thread.number)}
      >
        {thread.number}
      </button>
    </div>
  );
};

const DraftMark = ({
  draft,
  annotation,
  hintId,
}: {
  draft: DraftRegion;
  annotation: Annotation;
  hintId: string;
}): ReactElement => {
  const copy = useCopy();
  const ref = useRef<HTMLButtonElement>(null);
  const { isMarking } = annotation;
  const percents = regionPercents(draft);
  const label =
    draft.shape === 'point'
      ? copy.comments.draftPointLabel(percents.x, percents.y)
      : copy.comments.draftLabel(percents);

  // Marking starts from the button: the draft takes focus so the arrow keys work at once.
  useEffect(() => {
    if (isMarking) ref.current?.focus();
  }, [isMarking]);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>): void => {
    if (!isMarking) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      annotation.stopMarking(false);
      return;
    }
    const next = regionAfterKey(draft, event.key, {
      shiftKey: event.shiftKey,
      altKey: event.altKey,
    });
    if (next) {
      event.preventDefault();
      annotation.setDraft(next);
    }
  };

  // A button, so Enter (or Space) keeps the region; the arrow keys move and resize it.
  return (
    <button
      ref={ref}
      type="button"
      className={[
        'region-overlay__draft',
        draft.shape === 'point' ? 'region-overlay__draft--point' : '',
        isMarking ? 'region-overlay__draft--active' : '',
      ]
        .join(' ')
        .trim()}
      style={regionStyle(draft)}
      aria-label={label}
      aria-describedby={isMarking ? hintId : undefined}
      tabIndex={isMarking ? 0 : -1}
      onKeyDown={onKeyDown}
      onClick={() => {
        if (isMarking) annotation.stopMarking(true);
      }}
    />
  );
};

/**
 * Marks of a version's threads over its preview (numbered rectangles and pins), and the region
 * being drawn: a drag marks a rectangle, a click a pin; the keyboard moves a centred rectangle.
 */
export const RegionOverlay = ({ threads, annotation }: RegionOverlayProps): ReactElement => {
  const copy = useCopy();
  const hintId = useId();
  const startRef = useRef<ImagePoint | null>(null);
  const { isMarking, draft } = annotation;

  const pointOf = (event: PointerEvent<HTMLDivElement>): ImagePoint =>
    pointIn(event.currentTarget.getBoundingClientRect(), event.clientX, event.clientY);
  const onPointerDown = (event: PointerEvent<HTMLDivElement>): void => {
    if (!isMarking || event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const start = pointOf(event);
    startRef.current = start;
    annotation.setDraft(regionFromDrag(start, start));
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>): void => {
    const start = startRef.current;
    if (!isMarking || !start) return;
    annotation.setDraft(regionFromDrag(start, pointOf(event)));
  };
  const onPointerUp = (event: PointerEvent<HTMLDivElement>): void => {
    const start = startRef.current;
    if (!isMarking || !start) return;
    startRef.current = null;
    annotation.setDraft(regionFromDrag(start, pointOf(event)));
    annotation.stopMarking(true);
  };

  return (
    // A drawing surface for pointers; the keyboard marks the same region with the draft button.
    <div
      className={`region-overlay${isMarking ? ' region-overlay--marking' : ''}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={() => {
        startRef.current = null;
      }}
    >
      {threads.length > 0 ? (
        <div className="region-overlay__marks" role="group" aria-label={copy.comments.regionsLabel}>
          {threads.map((thread) => (
            <RegionMark key={thread.id} thread={thread} annotation={annotation} />
          ))}
        </div>
      ) : null}
      {draft ? <DraftMark draft={draft} annotation={annotation} hintId={hintId} /> : null}
      {isMarking ? (
        // Read with the draft; the panel shows the same hint beside the comment field.
        <p id={hintId} className="visually-hidden">
          {copy.comments.markingHint}
        </p>
      ) : null}
    </div>
  );
};
