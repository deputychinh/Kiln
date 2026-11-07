import { CardSize } from '@/enums/card-size.enum';
import { GallerySort } from '@/enums/gallery-sort.enum';
import type { Asset, AssetKind } from '@/interfaces/asset.interface';
import type { GallerySearch } from '@/interfaces/gallery.interface';

const KINDS: readonly AssetKind[] = ['image', 'model'];
const isKind = (value: unknown): value is AssetKind => KINDS.includes(value as AssetKind);
const isSort = (value: unknown): value is GallerySort =>
  Object.values(GallerySort).includes(value as GallerySort);
const isSize = (value: unknown): value is CardSize =>
  Object.values(CardSize).includes(value as CardSize);

/** The gallery's search params, keeping only known values and leaving defaults out of the URL. */
export const parseGallerySearch = (raw: Record<string, unknown>): GallerySearch => ({
  ...(isKind(raw.kind) ? { kind: raw.kind } : {}),
  ...(isSort(raw.sort) && raw.sort !== GallerySort.Newest ? { sort: raw.sort } : {}),
  ...(isSize(raw.size) && raw.size !== CardSize.Large ? { size: raw.size } : {}),
});

const byName = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

/**
 * The cards to show: the loaded pages filtered by kind and ordered as asked. Client-side over what
 * is loaded (the API pages newest first); "Load more" brings in more to filter and sort.
 */
export const visibleAssets = (assets: readonly Asset[], search: GallerySearch): Asset[] => {
  const kept = search.kind ? assets.filter((asset) => asset.kind === search.kind) : [...assets];
  return search.sort === GallerySort.Name
    ? kept.sort((a, b) => byName.compare(a.name, b.name))
    : kept;
};

/** Characters kept whole at the end of a long name, so versions and extensions stay readable. */
const TAIL_LENGTH = 8;

/**
 * A name split for a middle ellipsis: the head shrinks with an ellipsis, the tail always shows
 * ("sunset_matte_pai…v3_final"). Short names are not split.
 */
export const splitForMiddleEllipsis = (name: string): { head: string; tail: string } =>
  name.length <= TAIL_LENGTH * 2
    ? { head: name, tail: '' }
    : { head: name.slice(0, -TAIL_LENGTH), tail: name.slice(-TAIL_LENGTH) };

/** The search with one option set, or removed (back to its default) when `value` is undefined. */
export const withOption = <Key extends keyof GallerySearch>(
  search: GallerySearch,
  key: Key,
  value: GallerySearch[Key] | undefined,
): GallerySearch => {
  const next = { ...search };
  if (value === undefined) delete next[key];
  else next[key] = value;
  return next;
};
