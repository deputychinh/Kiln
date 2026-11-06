/** Why a file was refused before anything was sent. */
export enum UploadRejection {
  Unsupported = 'unsupported',
  Empty = 'empty',
  TooLarge = 'too_large',
}
