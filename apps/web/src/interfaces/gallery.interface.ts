import type { CardSize } from '@/enums/card-size.enum';
import type { GallerySort } from '@/enums/gallery-sort.enum';
import type { AssetKind } from '@/interfaces/asset.interface';

/** The gallery's view options in the URL (`/assets?kind=model&sort=name&size=small`); absent = default. */
export interface GallerySearch {
  /** Only assets of this kind (default: every kind). */
  kind?: AssetKind;
  /** Name order instead of newest first. */
  sort?: GallerySort;
  /** Small cards instead of large ones. */
  size?: CardSize;
}
