import type { DraftRegion } from '@/interfaces/comment.interface';
import { layoutBadges } from '@/utils/badge-layout.util';

const pin = (x: number, y: number): DraftRegion => ({ shape: 'point', x, y, width: 0, height: 0 });
const rect = (x: number, y: number): DraftRegion => ({
  shape: 'rect',
  x,
  y,
  width: 0.2,
  height: 0.2,
});

const apart = (a: [number, number], b: [number, number]): boolean =>
  Math.abs(a[0] - b[0]) >= 26 || Math.abs(a[1] - b[1]) >= 26;

describe('layoutBadges', () => {
  it('puts a rectangle badge on its corner and centres a pin badge on its point', () => {
    expect(layoutBadges([rect(0.25, 0.5), pin(0.5, 0.5)], 400, 200)).toEqual([
      [100, 100],
      [188, 88],
    ]);
  });

  it('keeps pins at the corners and edges inside the image', () => {
    expect(layoutBadges([pin(1, 1)], 400, 200)).toEqual([[376, 176]]);
    expect(layoutBadges([pin(0, 0)], 400, 200)).toEqual([[0, 0]]);
    expect(layoutBadges([rect(0.99, 0.99)], 400, 200)).toEqual([[376, 176]]);
  });

  it('moves a badge that would cover an earlier one to the nearest free place', () => {
    const placed = layoutBadges([rect(0.5, 0.5), rect(0.51, 0.51), pin(0.5, 0.5)], 400, 300);

    expect(placed[0]).toEqual([200, 150]);
    for (const [index, box] of placed.entries()) {
      for (const other of placed.slice(index + 1)) expect(apart(box, other)).toBe(true);
    }
  });

  it('keeps every badge inside and apart for many crowded marks', () => {
    const regions = Array.from({ length: 20 }, (_, index) => pin(0.5 + index * 0.001, 0.5));

    const placed = layoutBadges(regions, 512, 384);

    for (const [index, [x, y]] of placed.entries()) {
      expect(x).toBeGreaterThanOrEqual(0);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(512 - 24);
      expect(y).toBeLessThanOrEqual(384 - 24);
      for (const other of placed.slice(index + 1)) expect(apart([x, y], other)).toBe(true);
    }
  });

  it('keeps a badge on its own place when an image is too small for them all', () => {
    const placed = layoutBadges([pin(0.5, 0.5), pin(0.5, 0.5)], 24, 24);

    expect(placed).toEqual([
      [0, 0],
      [0, 0],
    ]);
  });
});
