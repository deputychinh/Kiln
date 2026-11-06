import { apiGet } from '@/api/client';
import { ASSET_PAGE_SIZE, ASSETS_PATH } from '@/constants/assets.constant';
import type { AssetDetail, AssetPage } from '@/interfaces/asset.interface';

/** GET /api/v1/assets: one newest-first page; pass `next_cursor` back for the next. */
export const listAssets = (cursor: string | null, signal?: AbortSignal): Promise<AssetPage> => {
  const query = new URLSearchParams({ limit: String(ASSET_PAGE_SIZE) });
  if (cursor) query.set('cursor', cursor);
  return apiGet<AssetPage>(`${ASSETS_PATH}?${query.toString()}`, signal);
};

/** GET /api/v1/assets/{id}: the asset with its versions. */
export const getAsset = (id: string, signal?: AbortSignal): Promise<AssetDetail> =>
  apiGet<AssetDetail>(`${ASSETS_PATH}/${encodeURIComponent(id)}`, signal);
