import { ButtonVariant, FilePickerButton, ICON_SIZE } from '@kiln/ui';
import { Upload } from 'lucide-react';
import type { ReactElement } from 'react';

import { UPLOAD_ACCEPT } from '@/constants/upload.constant';
import { useUploadQueue } from '@/features/uploads/context/UploadsContext';
import { useCopy } from '@/hooks/useCopy';

interface UploadButtonProps {
  /** The visible label (default "Upload"). */
  label?: string;
  variant?: ButtonVariant;
  /** Only for the one button focus returns to (the top bar's). */
  id?: string;
}

/** Opens the file picker; every picked file becomes a new asset in the page's upload queue. */
export const UploadButton = ({
  label,
  variant = ButtonVariant.Primary,
  id,
}: UploadButtonProps): ReactElement => {
  const copy = useCopy();
  const uploads = useUploadQueue();
  return (
    <FilePickerButton
      {...(id === undefined ? {} : { id })}
      variant={variant}
      icon={<Upload size={ICON_SIZE.sm} />}
      accept={UPLOAD_ACCEPT}
      onFiles={(files) => uploads.add(files)}
    >
      {label ?? copy.uploads.upload}
    </FilePickerButton>
  );
};
