import { ICON_SIZE } from '@kiln/ui';
import { Link } from '@tanstack/react-router';
import { ArrowLeft } from 'lucide-react';
import type { ReactElement } from 'react';

import { useCopy } from '@/hooks/useCopy';

/** Back to the list; `isCompactOnly` hides it when the list is already visible beside the detail. */
export const BackLink = ({ isCompactOnly = false }: { isCompactOnly?: boolean }): ReactElement => {
  const copy = useCopy();
  return (
    <Link
      to="/assets"
      search={true}
      className={`asset-detail__back${isCompactOnly ? ' asset-detail__back--compact' : ''}`}
    >
      <ArrowLeft size={ICON_SIZE.sm} aria-hidden="true" />
      {copy.assets.back}
    </Link>
  );
};
