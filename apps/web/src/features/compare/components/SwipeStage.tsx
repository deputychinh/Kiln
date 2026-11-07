import { type CSSProperties, type ReactElement, type SyntheticEvent, useState } from 'react';

import { SWIPE_START_PERCENT } from '@/constants/compare.constant';
import { useCopy } from '@/hooks/useCopy';
import type { ComparePair } from '@/interfaces/compare.interface';

/**
 * Both previews in one frame, split by a divider the slider (or arrow keys) moves: the left
 * version shows left of the divider and the right version right of it, as the pickers say.
 */
export const SwipeStage = ({
  pair,
  onThumbError,
}: {
  pair: ComparePair;
  onThumbError: (src: string) => void;
}): ReactElement => {
  const copy = useCopy();
  const [divider, setDivider] = useState(SWIPE_START_PERCENT);
  const { left, right } = pair;
  const style = { '--compare-divider': `${String(divider)}%` } as CSSProperties;
  const reportError = (event: SyntheticEvent<HTMLImageElement>): void =>
    onThumbError(event.currentTarget.src);
  return (
    <div className="compare-page__swipe">
      <div className="compare-page__sides" aria-hidden="true">
        <span>{copy.compare.pane(left.number)}</span>
        <span>{copy.compare.pane(right.number)}</span>
      </div>
      <div
        className="compare-page__stage"
        role="group"
        aria-label={copy.compare.swipeStage(left.number, right.number)}
        style={style}
      >
        <img
          className="compare-page__layer"
          src={left.thumbnail_url ?? ''}
          alt={copy.compare.previewAlt(left.number)}
          onError={reportError}
        />
        <img
          className="compare-page__layer compare-page__layer--right"
          src={right.thumbnail_url ?? ''}
          alt={copy.compare.previewAlt(right.number)}
          onError={reportError}
        />
        <span className="compare-page__divider" aria-hidden="true" />
      </div>
      <input
        className="compare-page__slider"
        type="range"
        min={0}
        max={100}
        value={divider}
        aria-label={copy.compare.swipeLabel(left.number, right.number)}
        onChange={(event) => setDivider(Number(event.target.value))}
      />
    </div>
  );
};
