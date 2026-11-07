import { type ReactElement, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

import { UploadStatus } from '@/enums/upload-status.enum';
import { useCopy } from '@/hooks/useCopy';
import type { UploadsApi } from '@/interfaces/upload.interface';

const IN_FLIGHT = new Set([
  UploadStatus.Queued,
  UploadStatus.Creating,
  UploadStatus.Uploading,
  UploadStatus.Completing,
]);

/**
 * What the upload queue does for the whole page, once, whichever panels are on screen: announce
 * every outcome (a version's too, when its asset is no longer open), warn before the page is left
 * with any upload in flight, and refuse files dropped outside a zone.
 */
export const UploadPageEffects = ({ uploads }: { uploads: UploadsApi }): ReactElement => {
  const copy = useCopy();
  const { items, outcomes, outcomeCount } = uploads;

  // A file dropped just outside a zone must not make the browser open it (and so leave the
  // page with every running upload): refuse drops no zone took.
  useEffect(() => {
    const refuseStrayDrop = (event: DragEvent): void => {
      if (event.defaultPrevented || !event.dataTransfer?.types.includes('Files')) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'none';
    };
    window.addEventListener('dragover', refuseStrayDrop);
    window.addEventListener('drop', refuseStrayDrop);
    return () => {
      window.removeEventListener('dragover', refuseStrayDrop);
      window.removeEventListener('drop', refuseStrayDrop);
    };
  }, []);

  // Leaving the page abandons uploads in flight: let the browser ask first.
  const isBusy = items.some((item) => IN_FLIGHT.has(item.status));
  useEffect(() => {
    if (!isBusy) return;
    const warn = (event: BeforeUnloadEvent): void => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [isBusy]);

  // The live region lives on <body>: the list pane is hidden on compact screens while an asset
  // is open. New outcomes queue up until the next frame, so files ending together are all heard;
  // clearing first makes a repeated outcome ("rock.png: Ready" twice) heard again.
  const liveRef = useRef<HTMLParagraphElement>(null);
  const announcedCountRef = useRef(outcomeCount);
  const pendingRef = useRef<string[]>([]);
  useEffect(() => {
    const fresh = Math.min(outcomeCount - announcedCountRef.current, outcomes.length);
    announcedCountRef.current = outcomeCount;
    if (fresh > 0)
      pendingRef.current.push(
        ...outcomes
          .slice(-fresh)
          .map((item) =>
            copy.uploads.announce(item.file.name, item.error ?? copy.uploads.status[item.status]),
          ),
      );
    const live = liveRef.current;
    if (!live || pendingRef.current.length === 0) return;
    live.textContent = '';
    const frame = requestAnimationFrame(() => {
      live.textContent = pendingRef.current.join(' ');
      pendingRef.current = [];
    });
    return () => cancelAnimationFrame(frame);
  }, [copy, outcomes, outcomeCount]);

  return createPortal(
    <p className="visually-hidden" aria-live="polite" ref={liveRef} />,
    document.body,
  );
};
