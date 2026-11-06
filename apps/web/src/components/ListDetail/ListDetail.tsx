import type { ReactElement, ReactNode } from 'react';

import { EXPANDED_MEDIA_QUERY } from '@/constants/layout.constant';
import { useMediaQuery } from '@/hooks/useMediaQuery';

import './ListDetail.css';

interface ListDetailProps {
  list: ReactNode;
  detail: ReactNode;
  /** An item is selected: below the expanded size class the detail replaces the list. */
  hasSelection: boolean;
  /** Names the detail pane, which scrolls on its own (and so takes focus) when expanded. */
  detailLabel: string;
}

/** Material 3 list-detail: one pane when compact or medium, two side by side when expanded. */
export const ListDetail = ({
  list,
  detail,
  hasSelection,
  detailLabel,
}: ListDetailProps): ReactElement => {
  const isExpanded = useMediaQuery(EXPANDED_MEDIA_QUERY);
  return (
    <div className={`list-detail list-detail--${hasSelection ? 'detail' : 'list'}`}>
      <div className="list-detail__list">{list}</div>
      <section
        className="list-detail__detail"
        aria-label={detailLabel}
        // eslint-disable-next-line jsx-a11y-x/no-noninteractive-tabindex -- the pane scrolls on its own when expanded, so keyboard users must be able to focus it (axe scrollable-region-focusable)
        tabIndex={isExpanded ? 0 : undefined}
      >
        {detail}
      </section>
    </div>
  );
};
