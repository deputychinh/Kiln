import { Dropzone } from '@kiln/ui';
import { type ReactElement, useEffect, useRef } from 'react';

import { UPLOAD_ACCEPT } from '@/constants/upload.constant';
import { UploadRow } from '@/features/uploads/components/UploadRow';
import { useCopy } from '@/hooks/useCopy';
import type {
  UploadItem,
  UploadPanelZone,
  UploadsApi,
  UploadTarget,
} from '@/interfaces/upload.interface';
import { uploadSummaryOf } from '@/utils/upload-summary.util';

import './UploadPanel.css';

interface UploadPanelProps {
  uploads: UploadsApi;
  /** Files become new versions of this asset; without it they become new assets. */
  target?: UploadTarget;
  /** Required with `target`: what this panel's zone and list are called. */
  zone?: UploadPanelZone;
}

/**
 * The dropzone and the list of files being uploaded. Shows only its own rows: new assets in the
 * gallery, new versions of one asset in its detail. Page-wide duties (announcing outcomes, the
 * leave-page warning, refusing stray drops) belong to `UploadPageEffects`, once per page.
 */
export const UploadPanel = ({ uploads, target, zone }: UploadPanelProps): ReactElement => {
  const copy = useCopy();
  const targetAssetId = target?.assetId ?? null;
  const isMine = (item: UploadItem): boolean => item.targetAssetId === targetAssetId;
  const items = uploads.items.filter(isMine);
  const summary = uploadSummaryOf(items);
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
    const focusTarget = row
      ? row.querySelector<HTMLButtonElement>('.upload-row__actions button')
      : panelRef.current.querySelector<HTMLButtonElement>('.dropzone button');
    focusTarget?.focus();
  }, [items.length]);
  const remove = (id: string): void => {
    focusIndexRef.current = items.findIndex((item) => item.id === id);
    uploads.remove(id);
  };

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
    </section>
  );
};
