import { CompareMode } from '@/enums/compare-mode.enum';
import type { AssetVersion } from '@/interfaces/asset.interface';
import type { ComparePair, CompareSearch } from '@/interfaces/compare.interface';

const MODES = new Set<string>(Object.values(CompareMode));

/** A version number from the URL: a positive whole number written as one, else nothing. */
const versionNumberOf = (raw: unknown): number | undefined => {
  const text = typeof raw === 'number' ? String(raw) : raw;
  if (typeof text !== 'string' || !/^[1-9]\d{0,8}$/.test(text)) return undefined;
  return Number(text);
};

/** The compare page's search params, keeping only what can be trusted. */
export const parseCompareSearch = (raw: Record<string, unknown>): CompareSearch => {
  const left = versionNumberOf(raw.left);
  const right = versionNumberOf(raw.right);
  const mode = typeof raw.mode === 'string' && MODES.has(raw.mode) ? raw.mode : undefined;
  return {
    ...(left === undefined ? {} : { left }),
    ...(right === undefined ? {} : { right }),
    ...(mode === undefined ? {} : { mode: mode as CompareMode }),
  };
};

/**
 * The pair to compare: the versions the URL names when both exist and differ; one named version
 * against the newest other one; otherwise the newest against the one before it.
 */
export const pickPair = (
  versions: readonly AssetVersion[],
  search: CompareSearch,
): ComparePair | null => {
  const newestFirst = [...versions].sort((a, b) => b.number - a.number);
  const [newest, previous] = newestFirst;
  if (!newest || !previous) return null;
  const find = (number?: number) => newestFirst.find((version) => version.number === number);
  const partnerOf = (version: AssetVersion): AssetVersion =>
    newestFirst.find((other) => other.number !== version.number) ?? previous;

  const left = find(search.left);
  const right = find(search.right);
  if (left && right && left.number !== right.number) return { left, right, isCorrected: false };
  if (left) return { left, right: partnerOf(left), isCorrected: true };
  if (right) return { left: partnerOf(right), right, isCorrected: true };
  const asked = search.left !== undefined || search.right !== undefined;
  return { left: previous, right: newest, isCorrected: asked };
};

/** Swipe lays one preview over the other, so both versions need one. */
export const canSwipe = (left: AssetVersion, right: AssetVersion): boolean =>
  Boolean(left.thumbnail_url && right.thumbnail_url);
