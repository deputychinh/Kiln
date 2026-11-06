import { PROCESSING_POLL_MAX, PROCESSING_POLL_MS } from '@/constants/assets.constant';
import type { AssetDetail } from '@/interfaces/asset.interface';

/** True while the worker still has to finish a version of this asset. */
export const hasProcessingVersion = (asset: AssetDetail | undefined): boolean =>
  asset?.versions.some((version) => version.status === 'processing') ?? false;

/** Poll while a version is processing, but give up after `PROCESSING_POLL_MAX` refreshes. */
export const processingPollInterval = (
  asset: AssetDetail | undefined,
  updateCount: number,
): number | false =>
  hasProcessingVersion(asset) && updateCount <= PROCESSING_POLL_MAX ? PROCESSING_POLL_MS : false;
