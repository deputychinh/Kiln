import { Badge, BadgeTone, Button, ButtonVariant, ProgressBar } from '@kiln/ui';
import { Link } from '@tanstack/react-router';
import type { ReactElement } from 'react';

import { UploadStatus } from '@/enums/upload-status.enum';
import { useCopy } from '@/hooks/useCopy';
import type { UploadItem } from '@/interfaces/upload.interface';

import './UploadRow.css';

interface UploadRowProps {
  item: UploadItem;
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
  onRemove: (id: string) => void;
}

const CANCELLABLE = new Set([
  UploadStatus.Queued,
  UploadStatus.Creating,
  UploadStatus.Uploading,
  UploadStatus.Completing,
]);
const WITH_PROGRESS = new Set([
  UploadStatus.Uploading,
  UploadStatus.Completing,
  UploadStatus.Processing,
]);
const TONE: Partial<Record<UploadStatus, BadgeTone>> = {
  [UploadStatus.Ready]: BadgeTone.Success,
  [UploadStatus.Uploaded]: BadgeTone.Success,
  [UploadStatus.Processing]: BadgeTone.Info,
  [UploadStatus.Failed]: BadgeTone.Danger,
  [UploadStatus.Cancelled]: BadgeTone.Warning,
};

/** One file in the upload list: its state, progress and what can be done with it. */
export const UploadRow = ({ item, onCancel, onRetry, onRemove }: UploadRowProps): ReactElement => {
  const copy = useCopy();
  const name = item.file.name;
  const isUploading = item.status === UploadStatus.Uploading;
  const statusText = isUploading
    ? `${copy.uploads.status.uploading} ${copy.uploads.progress(item.progress)}`
    : copy.uploads.status[item.status];
  const isRetryable =
    (item.status === UploadStatus.Failed && item.canRetry) ||
    item.status === UploadStatus.Cancelled;

  return (
    <li className="upload-row">
      <span className="upload-row__name" title={name}>
        {item.status === UploadStatus.Ready && item.assetId ? (
          <Link
            className="upload-row__link"
            to="/assets/$assetId"
            params={{ assetId: item.assetId }}
          >
            {name}
          </Link>
        ) : (
          name
        )}
      </span>
      <span className="upload-row__state">
        <Badge tone={TONE[item.status] ?? BadgeTone.Neutral}>{statusText}</Badge>
      </span>
      {WITH_PROGRESS.has(item.status) ? (
        <span className="upload-row__progress">
          <ProgressBar
            label={copy.uploads.progressLabel(name)}
            value={item.progress}
            valueText={copy.uploads.progress(item.progress)}
          />
        </span>
      ) : null}
      {item.error ? <p className="upload-row__error">{item.error}</p> : null}
      <span className="upload-row__actions">
        {CANCELLABLE.has(item.status) ? (
          <Button
            variant={ButtonVariant.Ghost}
            // The visible verb starts the accessible name (WCAG 2.5.3); the name says which file.
            aria-label={copy.uploads.cancel(name)}
            onClick={() => onCancel(item.id)}
          >
            {copy.uploads.cancelShort}
          </Button>
        ) : null}
        {isRetryable ? (
          <Button
            variant={ButtonVariant.Secondary}
            aria-label={copy.uploads.retry(name)}
            onClick={() => onRetry(item.id)}
          >
            {copy.uploads.retryShort}
          </Button>
        ) : null}
        {CANCELLABLE.has(item.status) || item.status === UploadStatus.Processing ? null : (
          <Button
            variant={ButtonVariant.Ghost}
            aria-label={copy.uploads.remove(name)}
            onClick={() => onRemove(item.id)}
          >
            {copy.uploads.removeShort}
          </Button>
        )}
      </span>
    </li>
  );
};
