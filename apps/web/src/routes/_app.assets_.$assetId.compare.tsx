import { createFileRoute } from '@tanstack/react-router';
import type { ReactElement } from 'react';

import { ComparePage } from '@/features/compare/components/ComparePage';
import { parseCompareSearch } from '@/utils/compare.util';

const CompareRoute = (): ReactElement => {
  const { assetId } = Route.useParams();
  return <ComparePage key={assetId} assetId={assetId} />;
};

/** Full width, outside the list-detail layout: two previews need the room. */
export const Route = createFileRoute('/_app/assets_/$assetId/compare')({
  validateSearch: parseCompareSearch,
  component: CompareRoute,
});
