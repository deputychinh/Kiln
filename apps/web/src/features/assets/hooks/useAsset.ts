import {
  replaceEqualDeep,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';

import {
  ASSET_LIST_QUERY_KEY,
  assetDetailQueryKey,
  THUMB_REFRESH_PER_KEY_MS,
} from '@/constants/assets.constant';
import { getAsset } from '@/features/assets/services/assets.service';
import { useKeyedThrottle } from '@/hooks/useKeyedThrottle';
import type { AssetDetail } from '@/interfaces/asset.interface';
import { hasProcessingVersion, keepSignedUrls, processingPollInterval } from '@/utils/asset.util';
import { withoutQuery } from '@/utils/signed-url.util';

/**
 * One asset; refreshed every few seconds while a version is processing (for a bounded time),
 * keeping still-valid preview URLs so polling does not re-download images, and refreshing the
 * gallery once processing ends so its card shows the new preview.
 */
export const useAsset = (
  id: string,
): { query: UseQueryResult<AssetDetail>; reportBrokenThumb: (src: string) => void } => {
  const queryClient = useQueryClient();
  const processingSinceRef = useRef<number | null>(null);
  const failedUrlsRef = useRef(new Set<string>());
  const refreshOnce = useKeyedThrottle(THUMB_REFRESH_PER_KEY_MS);
  const query = useQuery({
    queryKey: assetDetailQueryKey(id),
    queryFn: ({ signal }) => getAsset(id, signal),
    structuralSharing: (previous, next) =>
      replaceEqualDeep(
        previous,
        keepSignedUrls(previous as AssetDetail | undefined, next as AssetDetail, {
          failed: failedUrlsRef.current,
        }),
      ),
    refetchInterval: ({ state }) => {
      if (!hasProcessingVersion(state.data)) processingSinceRef.current = null;
      else processingSinceRef.current ??= Date.now();
      return processingPollInterval(state.data, processingSinceRef.current);
    },
  });

  const isProcessing = hasProcessingVersion(query.data);
  const wasProcessingRef = useRef(isProcessing);
  useEffect(() => {
    if (wasProcessingRef.current && !isProcessing) {
      void queryClient.invalidateQueries({ queryKey: ASSET_LIST_QUERY_KEY });
    }
    wasProcessingRef.current = isProcessing;
  }, [isProcessing, queryClient]);

  // A preview the browser could not load is never kept, and its object is re-signed once per
  // signature lifetime: an expired URL recovers, an object that is gone does not loop.
  const { refetch } = query;
  const reportBrokenThumb = useCallback(
    (src: string) => {
      failedUrlsRef.current.add(src);
      refreshOnce(withoutQuery(src), () => void refetch());
    },
    [refetch, refreshOnce],
  );

  return { query, reportBrokenThumb };
};
