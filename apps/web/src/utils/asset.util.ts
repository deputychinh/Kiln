import {
  PROCESSING_POLL_MAX_MS,
  PROCESSING_POLL_MS,
  SIGNED_URL_MIN_REMAINING_MS,
} from '@/constants/assets.constant';
import type { AssetDetail } from '@/interfaces/asset.interface';
import { keepSignedUrl } from '@/utils/signed-url.util';

/** True while the worker still has to finish a version of this asset. */
export const hasProcessingVersion = (asset: AssetDetail | undefined): boolean =>
  asset?.versions.some((version) => version.status === 'processing') ?? false;

/** Poll while a version is processing, for at most `PROCESSING_POLL_MAX_MS` since it started. */
export const processingPollInterval = (
  asset: AssetDetail | undefined,
  processingSince: number | null,
  now = Date.now(),
): number | false =>
  hasProcessingVersion(asset) &&
  processingSince !== null &&
  now - processingSince < PROCESSING_POLL_MAX_MS
    ? PROCESSING_POLL_MS
    : false;

/** The new asset, with still-valid signed preview URLs of the same objects kept from the old one. */
export const keepSignedUrls = (
  previous: AssetDetail | undefined,
  next: AssetDetail,
  now = Date.now(),
): AssetDetail => {
  if (!previous || previous.id !== next.id) return next;
  const versions = new Map(previous.versions.map((version) => [version.id, version]));
  return {
    ...next,
    thumbnail_url: keepSignedUrl({
      previous: previous.thumbnail_url,
      next: next.thumbnail_url,
      minRemainingMs: SIGNED_URL_MIN_REMAINING_MS,
      now,
    }),
    versions: next.versions.map((version) => ({
      ...version,
      thumbnail_url: keepSignedUrl({
        previous: versions.get(version.id)?.thumbnail_url,
        next: version.thumbnail_url,
        minRemainingMs: SIGNED_URL_MIN_REMAINING_MS,
        now,
      }),
    })),
  };
};
