import { CardSize } from '@/enums/card-size.enum';
import { GallerySort } from '@/enums/gallery-sort.enum';
import { anAsset } from '@/test/fake-api';
import { isFiltered, parseGallerySearch, visibleAssets, withOption } from '@/utils/gallery.util';

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

describe('review state in the gallery (KILN-11)', () => {
  const fixMe = anAsset({ id: 'r1', name: 'fix_me', review_state: 'changes_requested' });
  const done = anAsset({ id: 'r2', name: 'done', review_state: 'approved' });
  const waiting = anAsset({ id: 'r3', name: 'waiting', review_state: 'in_review' });
  const alsoFix = anAsset({ id: 'r4', name: 'also_fix', review_state: 'changes_requested' });
  const loaded = [done, fixMe, waiting, alsoFix];

  it('keeps a known review state from the URL and drops anything else', () => {
    expect(parseGallerySearch({ review: 'approved' })).toEqual({ review: 'approved' });
    expect(parseGallerySearch({ review: 'changes_requested', sort: 'attention' })).toEqual({
      review: 'changes_requested',
      sort: GallerySort.Attention,
    });
    expect(parseGallerySearch({ review: 'rejected' })).toEqual({});
    expect(parseGallerySearch({ review: ['approved'] })).toEqual({});
  });

  it('keeps only the assets in the chosen state, in order, with the kind filter too', () => {
    expect(visibleAssets(loaded, { review: 'changes_requested' })).toEqual([fixMe, alsoFix]);
    expect(visibleAssets([...loaded, crate], { review: 'in_review', kind: 'model' })).toEqual([
      crate,
    ]);
  });

  it('orders by what needs attention: changes requested, in review, approved, newest first in each', () => {
    expect(visibleAssets(loaded, { sort: GallerySort.Attention })).toEqual([
      fixMe,
      alsoFix,
      waiting,
      done,
    ]);
  });

  it('counts as filtered with a kind or a review state, not with a sort or a size', () => {
    expect(isFiltered({ review: 'approved' })).toBe(true);
    expect(isFiltered({ kind: 'image' })).toBe(true);
    expect(isFiltered({ sort: GallerySort.Attention, size: CardSize.Small })).toBe(false);
  });
});
