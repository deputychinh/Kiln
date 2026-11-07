import type { ReactElement } from 'react';

import { SkeletonShape } from '#ui/enums/skeleton-shape.enum';

import './Skeleton.css';

interface SkeletonProps {
  /** A 4:3 preview tile, a gallery card (tile and two text lines) or a line of text. */
  shape?: SkeletonShape;
}

/** A placeholder with the final size; the surrounding view announces loading once with `role="status"`. */
export const Skeleton = ({ shape = SkeletonShape.Line }: SkeletonProps): ReactElement =>
  shape === SkeletonShape.Card ? (
    <div className="skeleton skeleton--card" aria-hidden="true">
      <span className="skeleton__tile" />
      <span className="skeleton__line" />
      <span className="skeleton__line skeleton__line--short" />
    </div>
  ) : (
    <div className={`skeleton skeleton--${shape}`} aria-hidden="true" />
  );
