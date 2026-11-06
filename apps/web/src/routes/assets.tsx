import { createFileRoute, Outlet, useParams } from '@tanstack/react-router';
import type { ReactElement } from 'react';

import { ListDetail } from '@/components/ListDetail/ListDetail';
import { AssetGallery } from '@/features/assets/components/AssetGallery';
import { useCopy } from '@/hooks/useCopy';

const AssetsLayout = (): ReactElement => {
  const copy = useCopy();
  const { assetId } = useParams({ strict: false });
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
