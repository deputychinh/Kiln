/** Why a file was refused before anything was sent. */
export enum UploadRejection {
  Unsupported = 'unsupported',
  Empty = 'empty',
  TooLarge = 'too_large',
  NameTooLong = 'name_too_long',
  /** A version for an image asset that is not an image. */
  NotAnImage = 'not_an_image',
  /** A version for a model asset that is not a model. */
  NotAModel = 'not_a_model',
}
