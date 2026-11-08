import { type ReactElement, useCallback, useId, useState } from 'react';

import { ReviewDecision } from '@/features/reviews/components/ReviewDecision';
import { ReviewHistory } from '@/features/reviews/components/ReviewHistory';
import { useReviewHistory } from '@/features/reviews/hooks/useReviews';
import { useCopy } from '@/hooks/useCopy';
import type { AssetVersion } from '@/interfaces/asset.interface';

import './ReviewPanel.css';

interface ReviewPanelProps {
  assetId: string;
  versions: AssetVersion[];
  version: AssetVersion;
  onVersionChange: (versionId: string) => void;
}

/**
 * The Review tab: the chosen version's state, the decisions the state machine allows now with an
 * optional note, and the history. A decision names the state and revision it was made on; if
 * someone else decided first, the API refuses it and the panel says who won, keeping the note.
 */
export const ReviewPanel = ({
  assetId,
  versions,
  version,
  onVersionChange,
}: ReviewPanelProps): ReactElement => {
  const copy = useCopy();
  const selectId = useId();
  const [announcements, setAnnouncements] = useState<{ id: number; text: string }[]>([]);
  const announce = useCallback((text: string) => {
    setAnnouncements((current) => [...current.slice(-2), { id: Date.now() + Math.random(), text }]);
  }, []);
  const history = useReviewHistory(version.id);
  const newest = versions.at(-1);
  return (
    <div className="review-panel">
      {versions.length > 1 ? (
        <div className="review-panel__version">
          <label className="review-panel__label" htmlFor={selectId}>
            {copy.reviews.versionLabel}
          </label>
          <select
            id={selectId}
            className="review-panel__select"
            value={version.id}
            onChange={(event) => onVersionChange(event.target.value)}
          >
            {[...versions].reverse().map((option) => (
              <option key={option.id} value={option.id}>
                {copy.reviews.versionOption(option.number, option.id === newest?.id)}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <ReviewDecision key={version.id} assetId={assetId} version={version} announce={announce} />
      <ReviewHistory history={history} versionNumber={version.number} />
      <div className="visually-hidden" role="status" aria-live="polite">
        {announcements.map((item) => (
          <p key={item.id}>{item.text}</p>
        ))}
      </div>
    </div>
  );
};
