import type { CompareMode } from '@/enums/compare-mode.enum';
import type { AssetVersion } from '@/interfaces/asset.interface';

/** The compare page's URL state, already validated. */
export interface CompareSearch {
  left?: number;
  right?: number;
  mode?: CompareMode;
}

/** The two versions to show, and whether the URL asked for something else. */
export interface ComparePair {
  left: AssetVersion;
  right: AssetVersion;
  /** The URL named versions that do not exist (or the same one twice): replace it with this pair. */
  isCorrected: boolean;
}
