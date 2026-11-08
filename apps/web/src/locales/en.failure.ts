import type { Copy } from '@/interfaces/copy.interface';

/** English copy of why a version failed processing (moved out of en.ts to keep it short). */
export const enFailure: Copy['assets']['failure'] = {
  UPLOAD_CHANGED: 'The file changed after it was uploaded. Upload it again.',
  UNREADABLE_IMAGE: 'This is not a readable PNG, JPEG or WebP image.',
  IMAGE_TOO_LARGE: 'The image has too many pixels to preview.',
  PROCESSING_GAVE_UP: 'Processing failed several times. Upload the file again later.',
  UPLOAD_EXPIRED: 'The upload was never completed. Upload the file again.',
  UNREADABLE_MODEL:
    'This is not a glTF binary (.glb) Kiln can read. Compressed meshes (Draco, meshopt) and external files are not supported yet.',
  MODEL_TOO_LARGE:
    'The model is too large or too complex to preview (limits include 256 MB, 2 million triangles and 60 seconds of rendering).',
};
