import { Dropzone } from '@kiln/ui';
import { type ReactElement, useCallback, useRef } from 'react';

import { UPLOAD_ACCEPT } from '@/constants/upload.constant';
import { UploadList } from '@/features/uploads/components/UploadList';
import { useCopy } from '@/hooks/useCopy';
import type { UploadPanelZone, UploadsApi, UploadTarget } from '@/interfaces/upload.interface';

import './UploadPanel.css';

interface UploadPanelProps {
  uploads: UploadsApi;
  /** Files become new versions of this asset; without it they become new assets. */
  target?: UploadTarget;
  /** Required with `target`: what this panel's zone and list are called. */
  zone?: UploadPanelZone;
}

/** A dropzone with the list of its own uploads (new assets, or new versions of one asset). */
export const UploadPanel = ({ uploads, target, zone }: UploadPanelProps): ReactElement => {
  const copy = useCopy();
  const panelRef = useRef<HTMLElement>(null);
  const focusChooseButton = useCallback(
    () => panelRef.current?.querySelector<HTMLButtonElement>('.dropzone button') ?? null,
    [],
  );
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
      <UploadList
        uploads={uploads}
        target={target}
        listLabel={zone?.listLabel ?? copy.uploads.listLabel}
        fallbackFocus={focusChooseButton}
      />
    </section>
  );
};
