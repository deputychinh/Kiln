import { createContext, type ReactElement, type ReactNode, use } from 'react';

import { useUploads } from '@/features/uploads/hooks/useUploads';
import type { UploadsApi } from '@/interfaces/upload.interface';

const UploadsContext = createContext<UploadsApi | null>(null);

/**
 * One upload queue for the whole assets page: uploads keep running while the person opens
 * another asset or goes back to the list, and the concurrency limit covers every panel.
 */
export const UploadsProvider = ({ children }: { children: ReactNode }): ReactElement => (
  <UploadsContext value={useUploads()}>{children}</UploadsContext>
);

/** The page's upload queue; only inside `UploadsProvider`. */
export const useUploadQueue = (): UploadsApi => {
  const uploads = use(UploadsContext);
  if (!uploads) throw new Error('useUploadQueue must be used inside UploadsProvider');
  return uploads;
};
