/** The API's limit per file (`MAX_UPLOAD_BYTES`, 500 MiB). */
export const UPLOAD_MAX_BYTES = 500 * 1024 * 1024;
/** The API's limit for asset names (`ASSET_NAME_MAX_LENGTH`). */
export const ASSET_NAME_MAX_LENGTH = 120;
/** The API's limit for file names (`FILE_NAME_MAX_LENGTH`), in characters. */
export const FILE_NAME_MAX_LENGTH = 255;
/** Files sent at the same time; the rest wait in the queue. */
export const UPLOAD_CONCURRENCY = 2;
/** Content types the API accepts, by file extension (browsers report `.glb` as an empty type). */
export const UPLOAD_CONTENT_TYPES: Readonly<Record<string, string>> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
  glb: 'model/gltf-binary',
};
/** The file picker's `accept`: the same types, by MIME type and by extension. */
export const UPLOAD_ACCEPT = [
  ...new Set(Object.values(UPLOAD_CONTENT_TYPES)),
  ...Object.keys(UPLOAD_CONTENT_TYPES).map((extension) => `.${extension}`),
].join(',');
export const completionsPath = (versionId: string): string =>
  `/api/v1/asset-versions/${encodeURIComponent(versionId)}/completions`;
/** The `code` of an `ApiError` raised when storage itself refuses the file (e.g. an expired form). */
export const STORAGE_REJECTED_CODE = 'STORAGE_REJECTED';
/** The API's `code` when a completion was already recorded (a retry after a lost reply). */
export const ALREADY_COMPLETE_CODE = 'INVALID_STATUS_TRANSITION';
