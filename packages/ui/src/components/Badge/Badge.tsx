import type { ReactElement, ReactNode } from 'react';

import { BadgeTone } from '#ui/enums/badge-tone.enum';

import './Badge.css';

interface BadgeProps {
  /** Reinforces the label's meaning with colour (never the only signal). */
  tone?: BadgeTone;
  /** A leading icon (decorative: the label carries the meaning). */
  icon?: ReactNode;
  /** The label; it carries the meaning on its own. */
  children: ReactNode;
}

/** A short status or kind label on a soft tint; the text carries the meaning, the tone reinforces it. */
export const Badge = ({ tone = BadgeTone.Neutral, icon, children }: BadgeProps): ReactElement => (
  <span className={`badge badge--${tone}`}>
    {icon ? (
      <span className="badge__icon" aria-hidden="true">
        {icon}
      </span>
    ) : null}
    {children}
  </span>
);
