import { ICON_SIZE } from '@kiln/ui';
import { MousePointerClick } from 'lucide-react';
import type { ReactElement } from 'react';

import { useCopy } from '@/hooks/useCopy';

import './NoSelection.css';

/** The inspector before anything is selected (expanded layout): what to do to fill it. */
export const NoSelection = (): ReactElement => {
  const copy = useCopy();
  return (
    <div className="no-selection">
      <span className="no-selection__icon" aria-hidden="true">
        <MousePointerClick size={ICON_SIZE.lg} />
      </span>
      <p className="no-selection__text">{copy.assets.selectPrompt}</p>
    </div>
  );
};
