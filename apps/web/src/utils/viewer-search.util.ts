import type { ViewerSearch } from '@/interfaces/viewer.interface';
import { versionNumberOf } from '@/utils/compare.util';

/**
 * The viewer page's search params, keeping only a version number that can be trusted. Kept apart
 * from `viewer.util` because routes load with the app: nothing here may pull viewer code in.
 */
export const parseViewerSearch = (raw: Record<string, unknown>): ViewerSearch => {
  const version = versionNumberOf(raw.version);
  return version === undefined ? {} : { version };
};
