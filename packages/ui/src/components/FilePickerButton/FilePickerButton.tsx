import { type ReactElement, type ReactNode, type Ref, useRef } from 'react';

import { Button } from '#ui/components/Button/Button';
import { ButtonVariant } from '#ui/enums/button-variant.enum';

import './FilePickerButton.css';

interface FilePickerButtonProps {
  /** The visible label, e.g. "Upload". */
  children: ReactNode;
  /** A fuller accessible name when the label alone is ambiguous; it starts with the visible label (WCAG 2.5.3). */
  accessibleName?: string;
  /** A leading icon (decorative). */
  icon?: ReactNode;
  /** Primary by default; secondary or ghost where it is not the main action. */
  variant?: ButtonVariant;
  /** Passed to the file picker (`accept`); the caller still checks every file. */
  accept?: string;
  /** Allow several files at once (default) or exactly one. */
  isMultiple?: boolean;
  /** Called with the picked files, never with an empty list. */
  onFiles: (files: File[]) => void;
  /** The button, e.g. to move focus back to it. */
  ref?: Ref<HTMLButtonElement> | undefined;
}

/** A button that opens the system file picker: the keyboard and touch path to every file drop. */
export const FilePickerButton = ({
  children,
  accessibleName,
  icon,
  variant = ButtonVariant.Primary,
  accept,
  isMultiple = true,
  onFiles,
  ref,
}: FilePickerButtonProps): ReactElement => {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <span className="file-picker-button">
      <Button
        ref={ref}
        variant={variant}
        icon={icon}
        aria-label={accessibleName}
        onClick={() => inputRef.current?.click()}
      >
        {children}
      </Button>
      <input
        ref={inputRef}
        className="file-picker-button__input"
        type="file"
        accept={accept}
        multiple={isMultiple}
        hidden
        tabIndex={-1}
        onChange={(event) => {
          const files = Array.from(event.currentTarget.files ?? []);
          event.currentTarget.value = ''; // the same file can be picked again
          if (files.length > 0) onFiles(files);
        }}
      />
    </span>
  );
};
