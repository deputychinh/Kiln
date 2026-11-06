/** Where one browser upload is: queued → creating → uploading → completing → processing → ready. */
export enum UploadStatus {
  Queued = 'queued',
  Creating = 'creating',
  Uploading = 'uploading',
  Completing = 'completing',
  Processing = 'processing',
  Ready = 'ready',
  /** Uploaded, but the preview took longer than the polling window; the gallery shows it later. */
  Uploaded = 'uploaded',
  Failed = 'failed',
  Cancelled = 'cancelled',
}
