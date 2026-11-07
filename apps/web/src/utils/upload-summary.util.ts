import { UploadStatus } from '@/enums/upload-status.enum';
import type { UploadItem } from '@/interfaces/upload.interface';

const FINISHED = new Set([UploadStatus.Ready, UploadStatus.Uploaded]);

/** Files finished (ready, or uploaded and still processing) and failed, out of all `items`. */
export const uploadSummaryOf = (
  items: UploadItem[],
): { finished: number; failed: number; total: number } => ({
  finished: items.filter((item) => FINISHED.has(item.status)).length,
  failed: items.filter((item) => item.status === UploadStatus.Failed).length,
  total: items.length,
});
