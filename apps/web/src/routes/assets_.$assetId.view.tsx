import { createFileRoute } from '@tanstack/react-router';
import type { ReactElement } from 'react';

import { ViewerPage } from '@/features/viewer/components/ViewerPage';
import { parseViewerSearch } from '@/utils/viewer-search.util';

const ViewerRoute = (): ReactElement => {
  const { assetId } = Route.useParams();
  return <ViewerPage key={assetId} assetId={assetId} />;
};

/** Full width, outside the list-detail layout: the model needs the room (KILN-9). */
export const Route = createFileRoute('/assets_/$assetId/view')({
  validateSearch: parseViewerSearch,
  component: ViewerRoute,
});
