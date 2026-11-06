import type { ReactElement } from 'react';

import { SkeletonShape } from '#ui/enums/skeleton-shape.enum';

import './Skeleton.css';

interface SkeletonProps {
  /** A square tile (a card's preview) or a line of text. */
  shape?: SkeletonShape;
}

/** A placeholder block; the surrounding view announces loading once with `role="status"`. */
export const Skeleton = ({ shape = SkeletonShape.Line }: SkeletonProps): ReactElement => (
  <div className={`skeleton skeleton--${shape}`} aria-hidden="true" />
);
