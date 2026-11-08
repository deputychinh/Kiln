import { Badge, ICON_SIZE } from '@kiln/ui';
import { CircleAlert, CircleCheck, Clock } from 'lucide-react';
import type { ReactElement } from 'react';

import { REVIEW_STATE_TONE } from '@/constants/reviews.constant';
import { useCopy } from '@/hooks/useCopy';
import type { ReviewState } from '@/interfaces/review.interface';

const ICONS = { in_review: Clock, approved: CircleCheck, changes_requested: CircleAlert } as const;

/** A review state as an icon, a word and a tone: never colour alone (WCAG 1.4.1, KILN-11). */
export const ReviewBadge = ({ state }: { state: ReviewState }): ReactElement => {
  const copy = useCopy();
  const Icon = ICONS[state];
  return (
    <span className="review-badge" data-review-state={state}>
      <Badge tone={REVIEW_STATE_TONE[state]} icon={<Icon size={ICON_SIZE.sm} />}>
        {copy.reviews.state[state]}
      </Badge>
    </span>
  );
};
