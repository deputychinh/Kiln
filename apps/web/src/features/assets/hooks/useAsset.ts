import { useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';

import { ASSET_LIST_QUERY_KEY, THUMB_REFRESH_WINDOW_MS } from '@/constants/assets.constant';
import {
  assetDetailQueryOptions,
  markPreviewFailed,
} from '@/features/assets/services/asset-detail.query';
import { useKeyedThrottle } from '@/hooks/useKeyedThrottle';
import type { AssetDetail } from '@/interfaces/asset.interface';
import { hasProcessingVersion, processingPollInterval } from '@/utils/asset.util';
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
  const refreshOnce = useKeyedThrottle(THUMB_REFRESH_WINDOW_MS);
  const query = useQuery({
    ...assetDetailQueryOptions(id),
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
      markPreviewFailed(id, src);
      refreshOnce(withoutQuery(src), () => void refetch());
    },
    [id, refetch, refreshOnce],
  );

  return { query, reportBrokenThumb };
};
