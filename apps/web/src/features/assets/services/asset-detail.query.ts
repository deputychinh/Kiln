import { replaceEqualDeep } from '@tanstack/react-query';

import { assetDetailQueryKey } from '@/constants/assets.constant';
import { getAsset } from '@/features/assets/services/assets.service';
import type { AssetDetail, AssetDetailQuery } from '@/interfaces/asset.interface';
import { keepSignedUrls } from '@/utils/asset.util';

/** Broken preview URLs remembered per asset; old ones age out, they are re-signed long before. */
const FAILED_PREVIEWS_KEPT = 50;
const failedPreviews = new Map<string, Set<string>>();
const NONE: ReadonlySet<string> = new Set();

/** A preview URL the browser could not load: it is never kept again for this asset. */
export const markPreviewFailed = (assetId: string, src: string): void => {
  const failed = failedPreviews.get(assetId) ?? new Set<string>();
  failed.add(src);
  if (failed.size > FAILED_PREVIEWS_KEPT) failed.delete(failed.values().next().value ?? '');
  failedPreviews.set(assetId, failed);
};

/**
 * The one definition of an asset's detail query, shared by the detail view and the upload queue,
 * so whichever of them fetches stores the answer the same way: still-valid signed preview URLs are
 * kept (no re-download), failed ones never are (KILN-6, KILN-27, KILN-34).
 */
export const assetDetailQueryOptions = (id: string): AssetDetailQuery => ({
  queryKey: assetDetailQueryKey(id),
  queryFn: ({ signal }) => getAsset(id, signal),
  structuralSharing: (previous: unknown, next: unknown) =>
    replaceEqualDeep(
      previous,
      keepSignedUrls(previous as AssetDetail | undefined, next as AssetDetail, {
        failed: failedPreviews.get(id) ?? NONE,
      }),
    ),
});
