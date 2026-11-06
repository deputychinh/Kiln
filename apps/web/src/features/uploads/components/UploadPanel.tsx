import { Dropzone } from '@kiln/ui';
import { type ReactElement, useEffect, useRef } from 'react';

import { UPLOAD_ACCEPT } from '@/constants/upload.constant';
import { UploadRow } from '@/features/uploads/components/UploadRow';
import { useCopy } from '@/hooks/useCopy';
import type { UploadsApi } from '@/interfaces/upload.interface';

import './UploadPanel.css';

interface UploadPanelProps {
  uploads: UploadsApi;
}

/** The dropzone and the list of files being uploaded, with one polite announcement per outcome. */
export const UploadPanel = ({ uploads }: UploadPanelProps): ReactElement => {
  const copy = useCopy();
  const { items, summary } = uploads;
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

  const announcement = uploads.outcomes
    .map((item) =>
      copy.uploads.announce(item.file.name, item.error ?? copy.uploads.status[item.status]),
    )
    .join('. ');

  return (
    <section className="upload-panel" aria-label={copy.uploads.panelLabel} ref={panelRef}>
      <Dropzone
        label={copy.uploads.dropLabel}
        hint={copy.uploads.dropHint}
        buttonLabel={copy.uploads.choose}
        accept={UPLOAD_ACCEPT}
        onFiles={uploads.add}
      />
      {items.length > 0 ? (
        <>
          <p className="upload-panel__summary">
            {copy.uploads.summary(summary.finished, summary.total, summary.failed)}
          </p>
          <ul className="upload-panel__list" aria-label={copy.uploads.listLabel}>
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
      <p className="visually-hidden" aria-live="polite">
        {announcement}
      </p>
    </section>
  );
};
