import { createFileRoute } from '@tanstack/react-router';
import type { ReactElement } from 'react';

import { AssetDetail } from '@/features/assets/components/AssetDetail';

const AssetRoute = (): ReactElement => {
  const { assetId } = Route.useParams();
  // Keyed so a newly selected asset starts from its own loading state.
  return <AssetDetail key={assetId} assetId={assetId} />;
};

export const Route = createFileRoute('/assets/$assetId')({ component: AssetRoute });
