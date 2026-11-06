import type { ReactElement, ReactNode } from 'react';

import { BadgeTone } from '#ui/enums/badge-tone.enum';

import './Badge.css';

interface BadgeProps {
  /** Reinforces the label's meaning with colour (never the only signal). */
  tone?: BadgeTone;
  /** The label; it carries the meaning on its own. */
  children: ReactNode;
}

/** A short status or kind label; the text carries the meaning, the tone only reinforces it. */
export const Badge = ({ tone = BadgeTone.Neutral, children }: BadgeProps): ReactElement => (
  <span className={`badge badge--${tone}`}>{children}</span>
);
