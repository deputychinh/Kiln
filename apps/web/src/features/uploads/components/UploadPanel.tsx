import { Dropzone } from '@kiln/ui';
import { type ReactElement, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

import { UPLOAD_ACCEPT } from '@/constants/upload.constant';
import { UploadStatus } from '@/enums/upload-status.enum';
import { UploadRow } from '@/features/uploads/components/UploadRow';
import { useCopy } from '@/hooks/useCopy';
import type {
  UploadItem,
  UploadPanelZone,
  UploadsApi,
  UploadTarget,
} from '@/interfaces/upload.interface';

import './UploadPanel.css';

const FINISHED = new Set([UploadStatus.Ready, UploadStatus.Uploaded]);
const IN_FLIGHT = new Set([
  UploadStatus.Queued,
  UploadStatus.Creating,
  UploadStatus.Uploading,
  UploadStatus.Completing,
]);

interface UploadPanelProps {
  uploads: UploadsApi;
  /** Files become new versions of this asset; without it they become new assets. */
  target?: UploadTarget;
  /** Required with `target`: what this panel's zone and list are called. */
  zone?: UploadPanelZone;
}

/**
 * The dropzone and the list of files being uploaded, with one polite announcement per outcome.
 * Shows only its own rows: new assets in the gallery, new versions of one asset in its detail.
 */
export const UploadPanel = ({ uploads, target, zone }: UploadPanelProps): ReactElement => {
  const copy = useCopy();
  const targetAssetId = target?.assetId ?? null;
  const isMine = (item: UploadItem): boolean => item.targetAssetId === targetAssetId;
  const items = uploads.items.filter(isMine);
  const summary = {
    finished: items.filter((item) => FINISHED.has(item.status)).length,
    failed: items.filter((item) => item.status === UploadStatus.Failed).length,
    total: items.length,
  };
  const panelRef = useRef<HTMLElement>(null);
  // After Remove the pressed button is gone: focus the row that took its place (or the one
  // before it), or Choose files when the list is empty (WCAG 2.4.3).
  const focusIndexRef = useRef<number | null>(null);
  useEffect(() => {
    const index = focusIndexRef.current;
    if (index === null || !panelRef.current) return;
    focusIndexRef.current = null;
    const rows = panelRef.current.querySelectorAll('.upload-row');
    const row = rows[Math.min(index, rows.length - 1)];
    const target = row
      ? row.querySelector<HTMLButtonElement>('.upload-row__actions button')
      : panelRef.current.querySelector<HTMLButtonElement>('.dropzone button');
    target?.focus();
  }, [items.length]);
  const remove = (id: string): void => {
    focusIndexRef.current = items.findIndex((item) => item.id === id);
    uploads.remove(id);
  };

  // A file dropped just outside the zone must not make the browser open it (and so leave the
  // page with every running upload): refuse drops the zone did not take.
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
  const announcedCountRef = useRef(uploads.outcomeCount);
  const pendingRef = useRef<string[]>([]);
  const { outcomes, outcomeCount } = uploads;
  useEffect(() => {
    const fresh = Math.min(outcomeCount - announcedCountRef.current, outcomes.length);
    announcedCountRef.current = outcomeCount;
    if (fresh > 0)
      pendingRef.current.push(
        ...outcomes
          .slice(-fresh)
          .filter((item) => item.targetAssetId === targetAssetId)
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
  }, [copy, outcomes, outcomeCount, targetAssetId]);

  return (
    <section
      className="upload-panel"
      aria-label={zone?.panelLabel ?? copy.uploads.panelLabel}
      ref={panelRef}
    >
      <Dropzone
        label={zone?.dropLabel ?? copy.uploads.dropLabel}
        hint={zone?.hint ?? copy.uploads.dropHint}
        buttonLabel={zone?.buttonLabel ?? copy.uploads.choose}
        accept={zone?.accept ?? UPLOAD_ACCEPT}
        onFiles={(files) => uploads.add(files, target)}
      />
      {items.length > 0 ? (
        <>
          <p className="upload-panel__summary">
            {copy.uploads.summary(summary.finished, summary.total, summary.failed)}
          </p>
          <ul className="upload-panel__list" aria-label={zone?.listLabel ?? copy.uploads.listLabel}>
            {items.map((item) => (
              <UploadRow
                key={item.id}
                item={item}
                onCancel={uploads.cancel}
                onRetry={uploads.retry}
                onRemove={remove}
              />
            ))}
          </ul>
        </>
      ) : null}
      {createPortal(
        <p className="visually-hidden" aria-live="polite" ref={liveRef} />,
        document.body,
      )}
    </section>
  );
};
