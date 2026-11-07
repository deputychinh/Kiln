import { createFileRoute, Outlet, useParams } from '@tanstack/react-router';
import { type ReactElement, useEffect, useRef } from 'react';

import { ListDetail } from '@/components/ListDetail/ListDetail';
import { EXPANDED_MEDIA_QUERY, LARGE_MEDIA_QUERY } from '@/constants/layout.constant';
import { AssetGallery } from '@/features/assets/components/AssetGallery';
import { useAssetPages } from '@/features/assets/hooks/useAssetPages';
import { useCopy } from '@/hooks/useCopy';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { parseGallerySearch } from '@/utils/gallery.util';

const AssetsLayout = (): ReactElement => {
  const copy = useCopy();
  const { assetId } = useParams({ strict: false });
  const isExpanded = useMediaQuery(EXPANDED_MEDIA_QUERY);
  const isLarge = useMediaQuery(LARGE_MEDIA_QUERY);
  // The gallery's own query (shared cache, no extra request): an empty studio needs no inspector.
  const pages = useAssetPages();
  const isEmpty = pages.data?.pages.every((page) => page.items.length === 0) ?? false;
  const lastAssetIdRef = useRef<string | undefined>(assetId);

  // Back from a one-pane detail: return focus (and so the scroll position) to the card it came
  // from, instead of leaving keyboard users at the top of the page.
  useEffect(() => {
    const previous = lastAssetIdRef.current;
    lastAssetIdRef.current = assetId;
    if (assetId || !previous || isExpanded) return;
    document.querySelector<HTMLElement>(`[data-asset-id="${CSS.escape(previous)}"]`)?.focus();
  }, [assetId, isExpanded]);

  return (
    <ListDetail
      list={<AssetGallery />}
      detail={<Outlet />}
      hasSelection={Boolean(assetId)}
      detailLabel={copy.assets.detailLabel}
      // An empty inspector only earns its column on large windows, and never with no assets.
      isDetailHidden={!assetId && (isEmpty || !isLarge)}
    />
  );
};

/** The gallery's kind filter, sort and card size live in the URL; the detail keeps them. */
export const Route = createFileRoute('/assets')({
  validateSearch: parseGallerySearch,
  component: AssetsLayout,
});
