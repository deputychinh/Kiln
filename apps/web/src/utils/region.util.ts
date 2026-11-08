import {
  REGION_FINE_STEP,
  REGION_KEY_STEP,
  REGION_MIN_DRAG,
  REGION_MIN_SIZE,
} from '@/constants/comments.constant';
import type { DraftRegion, ImagePoint, Region, RegionInput } from '@/interfaces/comment.interface';

const PERCENT = 100;
/** Rounded so a region survives the trip through JSON without float noise. */
const DECIMALS = 1e6;

const clamp01 = (value: number): number => Math.min(1, Math.max(0, value));
const round = (value: number): number => Math.round(value * DECIMALS) / DECIMALS;

/** Where a pointer is on an element, normalised to it and kept inside it. */
export const pointIn = (rect: DOMRect, clientX: number, clientY: number): ImagePoint => ({
  x: rect.width > 0 ? clamp01((clientX - rect.left) / rect.width) : 0,
  y: rect.height > 0 ? clamp01((clientY - rect.top) / rect.height) : 0,
});

/** The region a drag from `start` to `end` marks: a rectangle, or a point for a short drag. */
export const regionFromDrag = (start: ImagePoint, end: ImagePoint): DraftRegion => {
  const width = Math.abs(end.x - start.x);
  const height = Math.abs(end.y - start.y);
  if (width < REGION_MIN_DRAG && height < REGION_MIN_DRAG) {
    return { shape: 'point', x: round(start.x), y: round(start.y), width: 0, height: 0 };
  }
  return {
    shape: 'rect',
    x: round(Math.min(start.x, end.x)),
    y: round(Math.min(start.y, end.y)),
    width: round(Math.max(width, REGION_MIN_SIZE)),
    height: round(Math.max(height, REGION_MIN_SIZE)),
  };
};

/** Keeps a draft inside the image: a rectangle never passes the right or bottom edge. */
export const fitRegion = (region: DraftRegion): DraftRegion => {
  if (region.shape === 'point')
    return { ...region, x: round(clamp01(region.x)), y: round(clamp01(region.y)) };
  const width = Math.min(1, Math.max(REGION_MIN_SIZE, region.width));
  const height = Math.min(1, Math.max(REGION_MIN_SIZE, region.height));
  return {
    shape: 'rect',
    x: round(Math.min(Math.max(0, region.x), 1 - width)),
    y: round(Math.min(Math.max(0, region.y), 1 - height)),
    width: round(width),
    height: round(height),
  };
};

const ARROWS: Record<string, [number, number]> = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
};

/**
 * The draft after an arrow key: arrows move it, Shift + arrows resize a rectangle (right and down
 * grow it); Alt takes a fine step. Null for any other key.
 */
export const regionAfterKey = (
  region: DraftRegion,
  key: string,
  { shiftKey = false, altKey = false }: { shiftKey?: boolean; altKey?: boolean } = {},
): DraftRegion | null => {
  const arrow = ARROWS[key];
  if (!arrow) return null;
  const step = altKey ? REGION_FINE_STEP : REGION_KEY_STEP;
  const [dx, dy] = arrow;
  if (shiftKey && region.shape === 'rect') {
    return fitRegion({
      ...region,
      width: region.width + dx * step,
      height: region.height + dy * step,
    });
  }
  return fitRegion({ ...region, x: region.x + dx * step, y: region.y + dy * step });
};

/** What the API takes. */
export const toRegionInput = (region: DraftRegion): RegionInput =>
  region.shape === 'point'
    ? { shape: 'point', x: region.x, y: region.y }
    : { shape: 'rect', x: region.x, y: region.y, width: region.width, height: region.height };

/** A stored region as a draft (to draw both the same way). */
export const toDraft = (region: Region): DraftRegion => ({
  shape: region.shape,
  x: region.x,
  y: region.y,
  width: region.width ?? 0,
  height: region.height ?? 0,
});

/** Percent positions for CSS, relative to the image's box. */
export const regionStyle = (
  region: DraftRegion,
): { left: string; top: string; width?: string; height?: string } => {
  const left = `${String(round(region.x * PERCENT))}%`;
  const top = `${String(round(region.y * PERCENT))}%`;
  if (region.shape === 'point') return { left, top };
  return {
    left,
    top,
    width: `${String(round(region.width * PERCENT))}%`,
    height: `${String(round(region.height * PERCENT))}%`,
  };
};

/** Whole percents for people ("40 by 40 percent at 30, 30"). */
export const regionPercents = (
  region: DraftRegion,
): { x: number; y: number; width: number; height: number } => ({
  x: Math.round(region.x * PERCENT),
  y: Math.round(region.y * PERCENT),
  width: Math.round(region.width * PERCENT),
  height: Math.round(region.height * PERCENT),
});

/** The start of a comment for a region's name, cut at a word near `max` characters. */
export const excerpt = (text: string, max: number): string => {
  const flat = text.replace(/\s+/g, ' ').trim();
  const characters = [...flat];
  if (characters.length <= max) return flat;
  const cut = characters.slice(0, max).join('');
  const lastSpace = cut.lastIndexOf(' ');
  return `${(lastSpace > max / 2 ? cut.slice(0, lastSpace) : cut).trimEnd()}…`;
};
