import {
  replaceEqualDeep,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import { ASSET_LIST_QUERY_KEY, assetDetailQueryKey } from '@/constants/assets.constant';
import { getAsset } from '@/features/assets/services/assets.service';
import type { AssetDetail } from '@/interfaces/asset.interface';
import { hasProcessingVersion, keepSignedUrls, processingPollInterval } from '@/utils/asset.util';

/**
 * One asset; refreshed every few seconds while a version is processing (for a bounded time),
 * keeping still-valid preview URLs so polling does not re-download images, and refreshing the
 * gallery once processing ends so its card shows the new preview.
 */
export const useAsset = (id: string): UseQueryResult<AssetDetail> => {
  const queryClient = useQueryClient();
  const processingSinceRef = useRef<number | null>(null);
  const query = useQuery({
    queryKey: assetDetailQueryKey(id),
    queryFn: ({ signal }) => getAsset(id, signal),
    structuralSharing: (previous, next) =>
      replaceEqualDeep(
        previous,
        keepSignedUrls(previous as AssetDetail | undefined, next as AssetDetail),
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

  return query;
};
