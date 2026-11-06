import {
  type InfiniteData,
  useInfiniteQuery,
  type UseInfiniteQueryResult,
} from '@tanstack/react-query';

import { ASSET_LIST_QUERY_KEY, ASSET_LIST_STALE_MS } from '@/constants/assets.constant';
import { listAssets } from '@/features/assets/services/assets.service';
import type { AssetPage } from '@/interfaces/asset.interface';

/** The gallery's pages, fetched one cursor at a time. */
export const useAssetPages = (): UseInfiniteQueryResult<InfiniteData<AssetPage, string | null>> =>
  useInfiniteQuery({
    queryKey: ASSET_LIST_QUERY_KEY,
    queryFn: ({ pageParam, signal }) => listAssets(pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor,
    staleTime: ASSET_LIST_STALE_MS,
  });
