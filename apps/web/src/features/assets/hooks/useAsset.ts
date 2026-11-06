import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { assetDetailQueryKey } from '@/constants/assets.constant';
import { getAsset } from '@/features/assets/services/assets.service';
import type { AssetDetail } from '@/interfaces/asset.interface';
import { processingPollInterval } from '@/utils/asset.util';

/** One asset; refreshed every few seconds while a version is processing, for a bounded time. */
export const useAsset = (id: string): UseQueryResult<AssetDetail> =>
  useQuery({
    queryKey: assetDetailQueryKey(id),
    queryFn: ({ signal }) => getAsset(id, signal),
    refetchInterval: (query) =>
      processingPollInterval(query.state.data, query.state.dataUpdateCount),
  });
