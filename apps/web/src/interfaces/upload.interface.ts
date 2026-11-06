import type { components } from '@/api/kiln.schema';
import type { UploadRejection } from '@/enums/upload-rejection.enum';
import type { UploadStatus } from '@/enums/upload-status.enum';

type Schemas = components['schemas'];

export type CreateAssetRequest = Schemas['CreateAssetRequest'];
export type PendingUpload = Schemas['PendingUploadOut'];
export type SignedUploadForm = Schemas['UploadOut'];

/** A file the API will accept, or why it will not. */
export type UploadDeclarationResult =
  | { declaration: CreateAssetRequest; rejection?: never }
  | { declaration?: never; rejection: UploadRejection };

/** One row of the upload list. */
export interface UploadItem {
  /** Local row id. */
  id: string;
  file: File;
  status: UploadStatus;
  /** Percent of the file sent to storage. */
  progress: number;
  /** What went wrong, in the person's words; set when `status` is failed. */
  error: string | null;
  /** False when retrying cannot help (a refused file, a preview that failed). */
  canRetry: boolean;
  /** One key per row, so a retry replays the asset instead of creating another. */
  idempotencyKey: string;
  assetId: string | null;
  versionId: string | null;
}

/** The part of `XMLHttpRequest` a storage upload uses (fetch has no upload progress). */
export interface StorageRequest {
  readonly status: number;
  readonly upload: {
    addEventListener: (
      type: 'progress',
      listener: (event: { lengthComputable: boolean; loaded: number; total: number }) => void,
    ) => void;
  };
  addEventListener: (type: 'load' | 'error' | 'abort', listener: () => void) => void;
  open: (method: string, url: string) => void;
  send: (body: FormData) => void;
  abort: () => void;
}

/** The upload queue as the gallery uses it (`useUploads`). */
export interface UploadsApi {
  items: UploadItem[];
  /** The rows that reached an end state in the last change (for a live announcement). */
  outcomes: UploadItem[];
  /** Files finished (ready, or uploaded and still processing) out of all rows. */
  summary: { finished: number; total: number };
  add: (files: File[]) => void;
  cancel: (id: string) => void;
  retry: (id: string) => void;
  remove: (id: string) => void;
}

/** The queue's state: its rows and the rows that just reached an end state. */
export interface UploadQueueState {
  items: UploadItem[];
  /** The rows that reached an end state in the last change, for one polite announcement. */
  outcomes: UploadItem[];
}
