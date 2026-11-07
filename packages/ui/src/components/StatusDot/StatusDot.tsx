import type { ReactElement, ReactNode } from 'react';

import { BadgeTone } from '#ui/enums/badge-tone.enum';

import './StatusDot.css';

interface StatusDotProps {
  /** The dot's colour; it only reinforces the label. */
  tone?: BadgeTone;
  /** Pulse the dot for work in progress (no pulse under reduced motion). */
  isActive?: boolean;
  /** The status in words; it carries the meaning on its own. */
  children: ReactNode;
}

/** A coloured dot followed by the status in words: compact, and colour is never the only signal. */
export const StatusDot = ({
  tone = BadgeTone.Neutral,
  isActive = false,
  children,
}: StatusDotProps): ReactElement => (
  <span className={`status-dot status-dot--${tone}${isActive ? ' status-dot--active' : ''}`}>
    <span className="status-dot__dot" aria-hidden="true" />
    {children}
  </span>
);
