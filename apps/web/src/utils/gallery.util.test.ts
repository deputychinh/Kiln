import { CardSize } from '@/enums/card-size.enum';
import { GallerySort } from '@/enums/gallery-sort.enum';
import { anAsset } from '@/test/fake-api';
import { parseGallerySearch, visibleAssets, withOption } from '@/utils/gallery.util';

const rock = anAsset({ id: 'a1', name: 'rock_albedo', kind: 'image' });
const crate = anAsset({ id: 'a2', name: 'Crate_wooden', kind: 'model' });
const tree10 = anAsset({ id: 'a3', name: 'tree_10', kind: 'model' });
const tree9 = anAsset({ id: 'a4', name: 'tree_9', kind: 'image' });
const newestFirst = [rock, crate, tree10, tree9];

describe('gallery search', () => {
  it('keeps known values and drops defaults and anything else', () => {
    expect(parseGallerySearch({ kind: 'model', sort: 'name', size: 'small' })).toEqual({
      kind: 'model',
      sort: GallerySort.Name,
      size: CardSize.Small,
    });
    expect(parseGallerySearch({ kind: 'video', sort: 'newest', size: 'large' })).toEqual({});
    expect(parseGallerySearch({ kind: 1, sort: ['name'], size: null })).toEqual({});
  });
});

describe('gallery option', () => {
  it('sets one option and leaves the others', () => {
    expect(withOption({ sort: GallerySort.Name }, 'kind', 'model')).toEqual({
      sort: GallerySort.Name,
      kind: 'model',
    });
  });

  it('removes an option going back to its default, without changing the search it was given', () => {
    const search = { kind: 'image', size: CardSize.Small } as const;

    expect(withOption(search, 'kind', undefined)).toEqual({ size: CardSize.Small });
    expect(search).toEqual({ kind: 'image', size: CardSize.Small });
  });
});

describe('visible assets', () => {
  it('shows every loaded asset newest first by default, without changing the list', () => {
    const shown = visibleAssets(newestFirst, {});

    expect(shown).toEqual(newestFirst);
    expect(shown).not.toBe(newestFirst);
  });

  it.each([
    ['image', [rock, tree9]],
    ['model', [crate, tree10]],
  ] as const)('keeps only the %s assets, in order', (kind, expected) => {
    expect(visibleAssets(newestFirst, { kind })).toEqual(expected);
  });

  it('orders by name, ignoring case and reading numbers as numbers', () => {
    expect(visibleAssets(newestFirst, { sort: GallerySort.Name }).map((a) => a.name)).toEqual([
      'Crate_wooden',
      'rock_albedo',
      'tree_9',
      'tree_10',
    ]);
  });

  it('filters and sorts together, and can end with nothing', () => {
    expect(visibleAssets(newestFirst, { kind: 'model', sort: GallerySort.Name })).toEqual([
      crate,
      tree10,
    ]);
    expect(visibleAssets([rock], { kind: 'model' })).toEqual([]);
  });
});
