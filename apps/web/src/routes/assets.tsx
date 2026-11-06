import { createFileRoute, Outlet, useParams } from '@tanstack/react-router';
import { type ReactElement, useEffect, useRef } from 'react';

import { ListDetail } from '@/components/ListDetail/ListDetail';
import { EXPANDED_MEDIA_QUERY } from '@/constants/layout.constant';
import { AssetGallery } from '@/features/assets/components/AssetGallery';
import { useCopy } from '@/hooks/useCopy';
import { useMediaQuery } from '@/hooks/useMediaQuery';

const AssetsLayout = (): ReactElement => {
  const copy = useCopy();
  const { assetId } = useParams({ strict: false });
  const isExpanded = useMediaQuery(EXPANDED_MEDIA_QUERY);
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
    />
  );
};

export const Route = createFileRoute('/assets')({ component: AssetsLayout });
