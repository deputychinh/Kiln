import { ViewerError } from '@/enums/viewer-error.enum';

/** The viewer page's route id (outside the `/assets` list-detail layout). */
export const VIEWER_ROUTE_ID = '/assets_/$assetId/view';
/** The worker refuses larger models (`MODEL_MAX_BYTES`), so no ready file is bigger. */
export const MODEL_VIEWER_MAX_BYTES = 256 * 1024 * 1024;
/** The worker's `MODEL_MAX_JSON_BYTES`: a larger JSON chunk is not read. */
export const GLB_MAX_JSON_BYTES = 16 * 1024 * 1024;
/**
 * Required extensions three's GLTFLoader handles without fetching a decoder: geometry compression
 * (Draco, meshopt) and Basis textures need one from a CDN, so they are refused.
 */
export const VIEWER_REQUIRED_EXTENSIONS: ReadonlySet<string> = new Set([
  'KHR_texture_transform',
  'KHR_mesh_quantization',
  'KHR_lights_punctual',
  'EXT_texture_webp',
  'EXT_texture_avif',
]);
export const VIEWER_MATERIAL_EXTENSION_PREFIX = 'KHR_materials_';
/** Errors a second attempt can fix (a dropped connection, an expired signed link). */
export const RETRYABLE_VIEWER_ERRORS: ReadonlySet<ViewerError> = new Set([ViewerError.Download]);
/** One key press or button press: 15° of orbit, 25 % closer or farther, a tenth of the view. */
export const ROTATE_STEP_RADIANS = Math.PI / 12;
export const ZOOM_STEP_FACTOR = 1.25;
export const PAN_STEP_RATIO = 0.1;
/** The framed view matches the still preview: 35° round, 25° from above (worker constants). */
export const VIEW_YAW_RADIANS = (35 * Math.PI) / 180;
export const VIEW_PITCH_RADIANS = (25 * Math.PI) / 180;
export const VIEW_FOV_DEGREES = 45;
/** Margin around the model's bounding sphere in the framed view. */
export const VIEW_FIT_MARGIN = 1.15;
/** How far the camera may come in or go out, relative to the bounding sphere's radius. */
export const VIEW_MIN_DISTANCE_RADII = 0.2;
export const VIEW_MAX_DISTANCE_RADII = 20;
export const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';
