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
import { useElementSize } from '@/hooks/useElementSize';
import type {
  Annotation,
  CommentThread,
  DraftRegion,
  ImagePoint,
  Region,
} from '@/interfaces/comment.interface';
import type { Copy } from '@/interfaces/copy.interface';
import { layoutBadges } from '@/utils/badge-layout.util';
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

/** A thread's region as drawn: a rectangle's outline, or a dot on a pin's point (decorative). */
const RegionShape = ({ thread, isSelected }: { thread: CommentThread; isSelected: boolean }) => {
  if (!thread.region) return null;
  const region = toDraft(thread.region);
  const block = region.shape === 'point' ? 'region-overlay__dot' : 'region-overlay__rect';
  const className = [
    block,
    isSelected ? `${block}--selected` : '',
    thread.resolved_at ? `${block}--resolved` : '',
  ]
    .join(' ')
    .trim();
  return <span className={className} style={regionStyle(region)} aria-hidden="true" />;
};

/**
 * A thread's numbered target. With the image measured, `position` is its place in px from the
 * badge layout (inside the image, never covering another badge); without, it sits on its region.
 */
const RegionBadge = ({
  thread,
  annotation,
  position,
}: {
  thread: CommentThread;
  annotation: Annotation;
  position: [number, number] | undefined;
}): ReactElement | null => {
  const copy = useCopy();
  if (!thread.region) return null;
  const region = toDraft(thread.region);
  const isSelected = annotation.selectedThreadId === thread.id;
  const style = position
    ? { left: `${String(position[0])}px`, top: `${String(position[1])}px` }
    : regionStyle(region);
  const className = [
    'region-overlay__badge',
    !position && region.shape === 'point' ? 'region-overlay__badge--centred' : '',
    isSelected ? 'region-overlay__badge--selected' : '',
    thread.resolved_at ? 'region-overlay__badge--resolved' : '',
  ]
    .join(' ')
    .trim();
  return (
    <button
      type="button"
      id={regionMarkId(thread.id)}
      className={className}
      style={{ left: style.left, top: style.top }}
      aria-label={regionLabel(thread, copy)}
      aria-current={isSelected ? 'true' : undefined}
      onClick={() => annotation.select(thread.id, { moveFocus: true })}
    >
      {thread.number}
    </button>
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
  const overlayRef = useRef<HTMLDivElement>(null);
  const size = useElementSize(overlayRef);
  const { isMarking, draft } = annotation;
  const marked = threads.filter(
    (thread): thread is CommentThread & { region: Region } => thread.region !== null,
  );
  const positions = size
    ? layoutBadges(
        marked.map((thread) => toDraft(thread.region)),
        size.width,
        size.height,
      )
    : undefined;

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
      ref={overlayRef}
      className={`region-overlay${isMarking ? ' region-overlay--marking' : ''}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={() => {
        startRef.current = null;
      }}
    >
      {marked.length > 0 ? (
        <div className="region-overlay__marks" role="group" aria-label={copy.comments.regionsLabel}>
          {marked.map((thread) => (
            <RegionShape
              key={`shape-${thread.id}`}
              thread={thread}
              isSelected={annotation.selectedThreadId === thread.id}
            />
          ))}
          {marked.map((thread, index) => (
            <RegionBadge
              key={thread.id}
              thread={thread}
              annotation={annotation}
              position={positions?.[index]}
            />
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
