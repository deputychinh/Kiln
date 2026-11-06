import { Dropzone } from '@kiln/ui';
import type { ReactElement } from 'react';

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
  const announcement = uploads.outcomes
    .map((item) =>
      copy.uploads.announce(item.file.name, item.error ?? copy.uploads.status[item.status]),
    )
    .join('. ');

  return (
    <section className="upload-panel" aria-label={copy.uploads.panelLabel}>
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
            {copy.uploads.summary(summary.finished, summary.total)}
          </p>
          <ul className="upload-panel__list" aria-label={copy.uploads.listLabel}>
            {items.map((item) => (
              <UploadRow
                key={item.id}
                item={item}
                onCancel={uploads.cancel}
                onRetry={uploads.retry}
                onRemove={uploads.remove}
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
