import { UploadStatus } from '@/enums/upload-status.enum';
import type { UploadItem, UploadsApi } from '@/interfaces/upload.interface';

/** One upload row; a new asset unless `targetAssetId` is set. */
export const anItem = (overrides: Partial<UploadItem> = {}): UploadItem => ({
  id: 'row-1',
  file: new File(['x'], 'rock.png', { type: 'image/png' }),
  status: UploadStatus.Queued,
  progress: 0,
  error: null,
  canRetry: true,
  idempotencyKey: 'key-1',
  assetId: null,
  versionId: null,
  targetAssetId: null,
  targetKind: null,
  ...overrides,
});

/** A queue that only reports what it is given; its actions are spies. */
export const uploadsWith = (
  items: UploadItem[],
  outcomes: UploadItem[] = [],
  outcomeCount = outcomes.length,
): UploadsApi => ({
  items,
  outcomes,
  outcomeCount,
  add: vi.fn(),
  cancel: vi.fn(),
  retry: vi.fn(),
  remove: vi.fn(),
});
