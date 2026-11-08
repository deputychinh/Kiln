import type { DraftRegion } from '@/interfaces/comment.interface';
import {
  excerpt,
  fitRegion,
  pointIn,
  regionAfterKey,
  regionFromDrag,
  regionPercents,
  regionStyle,
  toDraft,
  toRegionInput,
} from '@/utils/region.util';

const rect = (...[x, y, width, height]: [number, number, number, number]): DraftRegion => ({
  shape: 'rect',
  x,
  y,
  width,
  height,
});
const box = new DOMRect(100, 50, 400, 200);

describe('region.util', () => {
  it('normalises a pointer to the element and keeps it inside', () => {
    expect(pointIn(box, 300, 150)).toEqual({ x: 0.5, y: 0.5 });
    expect(pointIn(box, 0, 999)).toEqual({ x: 0, y: 1 });
    expect(pointIn(new DOMRect(100, 50, 0, 0), 300, 150)).toEqual({ x: 0, y: 0 });
  });

  it('makes a rectangle from a drag in any direction, from its top-left corner', () => {
    expect(regionFromDrag({ x: 0.75, y: 0.75 }, { x: 0.25, y: 0.5 })).toEqual(
      rect(0.25, 0.5, 0.5, 0.25),
    );
  });

  it('makes a pin from a drag shorter than 2 percent on both axes', () => {
    expect(regionFromDrag({ x: 0.3, y: 0.3 }, { x: 0.315, y: 0.31 })).toEqual({
      shape: 'point',
      x: 0.3,
      y: 0.3,
      width: 0,
      height: 0,
    });
    expect(regionFromDrag({ x: 0.3, y: 0.3 }, { x: 0.3, y: 0.32 }).shape).toBe('rect');
  });

  it('gives a thin drag the smallest size on its short side', () => {
    expect(regionFromDrag({ x: 0.1, y: 0.5 }, { x: 0.6, y: 0.5 })).toEqual(
      rect(0.1, 0.5, 0.5, 0.02),
    );
  });

  it('rounds coordinates to six decimals', () => {
    expect(regionFromDrag({ x: 1 / 3, y: 0 }, { x: 2 / 3, y: 0.5 })).toEqual(
      rect(0.333333, 0, 0.333333, 0.5),
    );
  });

  it('keeps a rectangle inside the image and never smaller than 2 percent', () => {
    expect(fitRegion(rect(0.9, 0.95, 0.4, 0.4))).toEqual(rect(0.6, 0.6, 0.4, 0.4));
    expect(fitRegion(rect(-0.1, -0.2, 1.5, 0.001))).toEqual(rect(0, 0, 1, 0.02));
    expect(fitRegion({ shape: 'point', x: 1.2, y: -1, width: 0, height: 0 })).toEqual({
      shape: 'point',
      x: 1,
      y: 0,
      width: 0,
      height: 0,
    });
  });

  it.each([
    ['ArrowRight', {}, rect(0.32, 0.3, 0.4, 0.4)],
    ['ArrowLeft', {}, rect(0.28, 0.3, 0.4, 0.4)],
    ['ArrowDown', {}, rect(0.3, 0.32, 0.4, 0.4)],
    ['ArrowUp', {}, rect(0.3, 0.28, 0.4, 0.4)],
    ['ArrowRight', { shiftKey: true }, rect(0.3, 0.3, 0.42, 0.4)],
    ['ArrowUp', { shiftKey: true }, rect(0.3, 0.3, 0.4, 0.38)],
    ['ArrowRight', { altKey: true }, rect(0.305, 0.3, 0.4, 0.4)],
  ])('moves or resizes with %s %o', (key, modifiers, expected) => {
    expect(regionAfterKey(rect(0.3, 0.3, 0.4, 0.4), key, modifiers)).toEqual(expected);
  });

  it('ignores other keys and moves a pin instead of resizing it', () => {
    expect(regionAfterKey(rect(0.3, 0.3, 0.4, 0.4), 'a')).toBeNull();
    expect(
      regionAfterKey({ shape: 'point', x: 0.5, y: 0.5, width: 0, height: 0 }, 'ArrowRight', {
        shiftKey: true,
      }),
    ).toEqual({ shape: 'point', x: 0.52, y: 0.5, width: 0, height: 0 });
  });

  it('sends a rectangle with its size and a pin without one', () => {
    expect(toRegionInput(rect(0.1, 0.2, 0.3, 0.4))).toEqual({
      shape: 'rect',
      x: 0.1,
      y: 0.2,
      width: 0.3,
      height: 0.4,
    });
    expect(toRegionInput({ shape: 'point', x: 0.1, y: 0.2, width: 0, height: 0 })).toEqual({
      shape: 'point',
      x: 0.1,
      y: 0.2,
    });
  });

  it('reads a stored region as a draft', () => {
    expect(toDraft({ shape: 'point', x: 0.1, y: 0.2, width: null, height: null })).toEqual({
      shape: 'point',
      x: 0.1,
      y: 0.2,
      width: 0,
      height: 0,
    });
  });

  it('places a region in percent of the image box', () => {
    expect(regionStyle(rect(0.25, 0.5, 0.5, 0.125))).toEqual({
      left: '25%',
      top: '50%',
      width: '50%',
      height: '12.5%',
    });
    expect(regionStyle({ shape: 'point', x: 0.1, y: 1, width: 0, height: 0 })).toEqual({
      left: '10%',
      top: '100%',
    });
    expect(regionPercents(rect(0.333, 0.5, 0.25, 0.4))).toEqual({
      x: 33,
      y: 50,
      width: 25,
      height: 40,
    });
  });

  it('names a region by the start of its comment, cut at a word', () => {
    expect(excerpt('Short', 40)).toBe('Short');
    expect(excerpt('Line one\n  line two', 40)).toBe('Line one line two');
    expect(excerpt('The rim is too bright and the edge glows a lot', 30)).toBe(
      'The rim is too bright and the…',
    );
    expect(excerpt('x'.repeat(50), 10)).toBe(`${'x'.repeat(10)}…`);
    expect(excerpt('🎨'.repeat(12), 10)).toBe(`${'🎨'.repeat(10)}…`);
  });
});

/** A small seeded generator (mulberry32), so a failing case can be replayed. */
const seeded = (seed: number): (() => number) => {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

/** What the API checks, after the region went through JSON as the browser sends it. */
const breaksTheApiRules = (region: DraftRegion): string | null => {
  const sent = JSON.parse(JSON.stringify(region)) as DraftRegion;
  const { x, y, width, height } = sent;
  if (!(x >= 0 && x <= 1 && y >= 0 && y <= 1)) return 'position';
  if (sent.shape === 'point') return width === 0 && height === 0 ? null : 'point size';
  if (width < 0.01 || height < 0.01) return 'too small';
  if (x + width > 1 || y + height > 1) return 'past an edge';
  return null;
};

describe('region.util drags (seeded properties)', () => {
  const EDGE_ENDS: ((random: () => number) => { x: number; y: number })[] = [
    (random) => ({ x: 1, y: random() }),
    (random) => ({ x: 0, y: random() }),
    (random) => ({ x: random(), y: 1 }),
    (random) => ({ x: random(), y: 0 }),
    () => ({ x: 1, y: 1 }),
    (random) => ({ x: 1 - random() * 0.004, y: random() }), // a narrow drag hugging the edge
  ];

  it.each([1, 2, 3, 42, 2026])(
    'every drag ending on an edge gives a region the API accepts (seed %i, 6,000 drags)',
    (seed) => {
      const random = seeded(seed);
      for (let index = 0; index < 1000; index += 1) {
        for (const end of EDGE_ENDS) {
          const start =
            index % 3 === 0
              ? { x: 1 - random() * 0.003, y: random() } // starts right at the edge too
              : { x: random(), y: random() };
          const region = regionFromDrag(start, end(random));
          expect(breaksTheApiRules(region), JSON.stringify({ seed, start, region })).toBeNull();
        }
      }
    },
  );

  it('keeps a narrow drag at the right edge inside the image at the smallest width', () => {
    expect(regionFromDrag({ x: 0.997, y: 0.2 }, { x: 0.999, y: 0.6 })).toEqual(
      rect(0.98, 0.2, 0.02, 0.4),
    );
  });

  it('keeps keyboard moves and resizes inside the image, whatever the steps', () => {
    const random = seeded(7);
    const keys = ['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown'];
    let region: DraftRegion = rect(0.3, 0.3, 0.4, 0.4);
    for (let step = 0; step < 5000; step += 1) {
      const key = keys[Math.floor(random() * keys.length)] ?? 'ArrowRight';
      region =
        regionAfterKey(region, key, { shiftKey: random() < 0.5, altKey: random() < 0.3 }) ?? region;
      expect(breaksTheApiRules(region), JSON.stringify({ step, region })).toBeNull();
    }
  });
});
