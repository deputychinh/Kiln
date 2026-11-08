import { BADGE_GAP_PX, BADGE_SEARCH_RINGS, BADGE_SIZE_PX } from '@/constants/comments.constant';
import type { DraftRegion } from '@/interfaces/comment.interface';

const STRIDE = BADGE_SIZE_PX + BADGE_GAP_PX;

const clamp = (value: number, max: number): number =>
  Math.min(Math.max(0, value), Math.max(0, max));

/** Where a mark's badge wants to be: a rectangle's top-left corner, or centred on a pin. */
const anchorOf = (region: DraftRegion, width: number, height: number): [number, number] =>
  region.shape === 'point'
    ? [region.x * width - BADGE_SIZE_PX / 2, region.y * height - BADGE_SIZE_PX / 2]
    : [region.x * width, region.y * height];

const overlaps = (a: [number, number], b: [number, number]): boolean =>
  Math.abs(a[0] - b[0]) < STRIDE && Math.abs(a[1] - b[1]) < STRIDE;

/** Neighbouring places by ring, nearest first: one badge stride apart on each axis. */
const OFFSETS: [number, number][] = Array.from({ length: BADGE_SEARCH_RINGS }, (_, index) => {
  const ring = index + 1;
  const places: [number, number][] = [];
  for (let dx = -ring; dx <= ring; dx += 1) {
    for (let dy = -ring; dy <= ring; dy += 1) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) === ring) places.push([dx * STRIDE, dy * STRIDE]);
    }
  }
  return places.sort((a, b) => Math.hypot(...a) - Math.hypot(...b));
}).flat();

/**
 * Pixel positions (top-left) for the badges of `regions`, in order, on an image `width` ×
 * `height`: each badge stays inside the image, and a badge that would cover an earlier one moves
 * to the nearest free place, so every target keeps its full 24 px (WCAG 2.5.8). When the image
 * is too crowded for that, a badge keeps its own place.
 */
export const layoutBadges = (
  regions: DraftRegion[],
  width: number,
  height: number,
): [number, number][] => {
  const maxX = width - BADGE_SIZE_PX;
  const maxY = height - BADGE_SIZE_PX;
  const placed: [number, number][] = [];
  for (const region of regions) {
    const [anchorX, anchorY] = anchorOf(region, width, height);
    const wanted: [number, number] = [clamp(anchorX, maxX), clamp(anchorY, maxY)];
    const free = [[0, 0] as [number, number], ...OFFSETS]
      .map(([dx, dy]): [number, number] => [
        clamp(wanted[0] + dx, maxX),
        clamp(wanted[1] + dy, maxY),
      ])
      .find((candidate) => placed.every((other) => !overlaps(candidate, other)));
    placed.push(free ?? wanted);
  }
  return placed;
};
