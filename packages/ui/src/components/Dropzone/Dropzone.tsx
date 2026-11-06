import { type DragEvent, type ReactElement, useId, useRef, useState } from 'react';

import { Button } from '#ui/components/Button/Button';
import { ButtonVariant } from '#ui/enums/button-variant.enum';

import './Dropzone.css';

interface DropzoneProps {
  /** What to drop here; also names the zone. */
  label: string;
  /** Limits worth knowing before dropping, e.g. the accepted types and size. */
  hint?: string;
  /** The file button (a primary action, 44 px): the keyboard and touch alternative to dragging (WCAG 2.5.7). */
  buttonLabel: string;
  /** Passed to the file picker (`accept`); dropped files are not filtered, the caller checks them. */
  accept?: string;
  /** Called with the dropped or picked files, never with an empty list. */
  onFiles: (files: File[]) => void;
}

const carriesFiles = (event: DragEvent): boolean =>
  Array.from(event.dataTransfer?.types ?? []).includes('Files');

/** Drop files on it or pick them with its button. */
export const Dropzone = ({
  label,
  hint,
  buttonLabel,
  accept,
  onFiles,
}: DropzoneProps): ReactElement => {
  const labelId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  // dragenter/dragleave fire for every child crossed; count them to know when the drag left.
  const depthRef = useRef(0);
  const [isActive, setIsActive] = useState(false);

  const take = (files: FileList | null | undefined): void => {
    const list = Array.from(files ?? []);
    if (list.length > 0) onFiles(list);
  };

  return (
    <div
      className={isActive ? 'dropzone dropzone--active' : 'dropzone'}
      role="group"
      aria-labelledby={labelId}
      onDragEnter={(event) => {
        if (!carriesFiles(event)) return;
        depthRef.current += 1;
        setIsActive(true);
      }}
      onDragLeave={(event) => {
        if (!carriesFiles(event)) return;
        depthRef.current = Math.max(0, depthRef.current - 1);
        if (depthRef.current === 0) setIsActive(false);
      }}
      onDragOver={(event) => {
        if (!carriesFiles(event)) return;
        event.preventDefault(); // allows the drop
        event.dataTransfer.dropEffect = 'copy';
      }}
      onDrop={(event) => {
        event.preventDefault(); // the browser would otherwise open the file
        depthRef.current = 0;
        setIsActive(false);
        take(event.dataTransfer?.files);
      }}
    >
      <p id={labelId} className="dropzone__label">
        {label}
      </p>
      {hint ? <p className="dropzone__hint">{hint}</p> : null}
      <Button variant={ButtonVariant.Primary} onClick={() => inputRef.current?.click()}>
        {buttonLabel}
      </Button>
      <input
        ref={inputRef}
        className="dropzone__input"
        type="file"
        accept={accept}
        multiple
        hidden
        tabIndex={-1}
        onChange={(event) => {
          take(event.currentTarget.files);
          event.currentTarget.value = ''; // the same file can be picked again
        }}
      />
    </div>
  );
};
