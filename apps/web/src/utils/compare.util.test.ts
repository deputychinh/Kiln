import { aVersion } from '@/test/fake-api';
import { canSwipe, parseCompareSearch, pickPair } from '@/utils/compare.util';

const v = (number: number, overrides = {}) =>
  aVersion({ id: `v${String(number)}`, number, ...overrides });

describe('pickPair', () => {
  const versions = [v(1), v(2), v(3)];

  it('shows the newest version against the one before it by default', () => {
    expect(pickPair(versions, {})).toMatchObject({
      left: { number: 2 },
      right: { number: 3 },
      isCorrected: false,
    });
  });

  it('shows the versions the URL names, in either order', () => {
    expect(pickPair(versions, { left: 3, right: 1 })).toMatchObject({
      left: { number: 3 },
      right: { number: 1 },
      isCorrected: false,
    });
  });

  it.each([[{ left: 8, right: 9 }], [{ left: 7 }], [{ left: 2, right: 2 }]])(
    'falls back to the default pair and asks for the URL to be corrected for %j',
    (search) => {
      expect(pickPair(versions, search)).toMatchObject({
        left: { number: 2 },
        right: { number: 3 },
        isCorrected: true,
      });
    },
  );

  it('keeps one valid side and fills the other with its neighbour', () => {
    expect(pickPair(versions, { left: 1 })).toMatchObject({
      left: { number: 1 },
      right: { number: 3 },
      isCorrected: true,
    });
  });

  it('has nothing to compare with fewer than two versions', () => {
    expect(pickPair([v(1)], {})).toBeNull();
    expect(pickPair([], {})).toBeNull();
  });
});

describe('parseCompareSearch', () => {
  it('keeps positive whole numbers and a known mode', () => {
    expect(parseCompareSearch({ left: '2', right: 3, mode: 'swipe' })).toEqual({
      left: 2,
      right: 3,
      mode: 'swipe',
    });
  });

  it.each([
    [{ left: '0' }],
    [{ left: '-1' }],
    [{ left: '1.5' }],
    [{ left: 'x' }],
    [{ left: '1e3' }],
    [{ left: '1234567890' }],
    [{ mode: 'diff' }],
  ])('drops what is not a version number or a mode: %j', (raw) => {
    expect(parseCompareSearch(raw)).toEqual({});
  });
});

describe('canSwipe', () => {
  it('needs a preview on both sides', () => {
    expect(canSwipe(v(1), v(2))).toBe(true);
    expect(canSwipe(v(1), v(2, { thumbnail_url: null, status: 'processing' }))).toBe(false);
  });
});
