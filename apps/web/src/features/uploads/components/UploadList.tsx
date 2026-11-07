import { type ReactElement, useEffect, useRef } from 'react';

import { UploadRow } from '@/features/uploads/components/UploadRow';
import { useCopy } from '@/hooks/useCopy';
import type { UploadItem, UploadsApi, UploadTarget } from '@/interfaces/upload.interface';
import { uploadSummaryOf } from '@/utils/upload-summary.util';

import './UploadList.css';

interface UploadListProps {
  uploads: UploadsApi;
  /** Only the versions of this asset; without it, only new assets. */
  target?: UploadTarget | undefined;
  /** Names the list, e.g. "Uploads" or "New versions of rock". */
  listLabel: string;
  /** Show "1 of 2 uploaded" above the rows (the tray shows it in its header instead). */
  hasSummary?: boolean;
  /** Where focus goes when the last row is removed (the button that adds files). */
  fallbackFocus: () => HTMLElement | null;
}

/**
 * The files being uploaded to one place (new assets, or new versions of one asset): each with its
 * state, progress and actions. Page-wide duties (announcing outcomes, the leave-page warning,
 * refusing stray drops) belong to `UploadPageEffects`, once per page.
 */
export const UploadList = ({
  uploads,
  target,
  listLabel,
  hasSummary = true,
  fallbackFocus,
}: UploadListProps): ReactElement | null => {
  const copy = useCopy();
  const targetAssetId = target?.assetId ?? null;
  const isMine = (item: UploadItem): boolean => item.targetAssetId === targetAssetId;
  const items = uploads.items.filter(isMine);
  const summary = uploadSummaryOf(items);
  const listRef = useRef<HTMLUListElement>(null);
  // After Remove the pressed button is gone: focus the row that took its place (or the one
  // before it), or the button that adds files when the list is empty (WCAG 2.4.3).
  const focusIndexRef = useRef<number | null>(null);
  useEffect(() => {
    const index = focusIndexRef.current;
    if (index === null) return;
    focusIndexRef.current = null;
    const rows = listRef.current?.querySelectorAll('.upload-row') ?? [];
    const row = rows[Math.min(index, rows.length - 1)];
    const focusTarget = row
      ? row.querySelector<HTMLButtonElement>('.upload-row__actions button')
      : fallbackFocus();
    focusTarget?.focus();
  }, [items.length, fallbackFocus]);
  const remove = (id: string): void => {
    focusIndexRef.current = items.findIndex((item) => item.id === id);
    uploads.remove(id);
  };

  if (items.length === 0) return null;
  return (
    <div className="upload-list">
      {hasSummary ? (
        <p className="upload-list__summary">
          {copy.uploads.summary(summary.finished, summary.total, summary.failed)}
        </p>
      ) : null}
      <ul className="upload-list__rows" aria-label={listLabel} ref={listRef}>
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
    </div>
  );
};
