import { BadgeTone } from '@kiln/ui';

import type { VersionStatus } from '@/interfaces/asset.interface';

export const ASSETS_PATH = '/api/v1/assets';
/** One page of the gallery: four rows of six on a wide screen. */
export const ASSET_PAGE_SIZE = 24;
/** Signed preview URLs live 15 min; keeping the list fresh for 5 keeps image cache keys stable. */
export const ASSET_LIST_STALE_MS = 5 * 60_000;
export const PROCESSING_POLL_MS = 3_000;
/** Five minutes of polling per processing spell; a stuck worker must not keep the tab busy. */
export const PROCESSING_POLL_MAX_MS = 5 * 60_000;
/** Keep an already-loaded signed URL while it stays valid this long (until KILN-27 makes them stable). */
export const SIGNED_URL_MIN_REMAINING_MS = 2 * 60_000;
/** How often relative times ("2 minutes ago") are recomputed. */
export const RELATIVE_TIME_TICK_MS = 60_000;
/** At most one refetch of signed URLs per minute when previews fail to load. */
export const THUMB_REFRESH_MIN_MS = 60_000;

export const ASSET_LIST_QUERY_KEY = ['assets', 'list'] as const;
export const assetDetailQueryKey = (id: string): readonly ['assets', 'detail', string] =>
  ['assets', 'detail', id] as const;

export const VERSION_STATUS_TONE: Record<VersionStatus, BadgeTone> = {
  pending_upload: BadgeTone.Neutral,
  processing: BadgeTone.Info,
  ready: BadgeTone.Success,
  failed: BadgeTone.Danger,
};
