import { type ReactElement, type ReactNode, useState } from 'react';

import { TooltipPlacement } from '#ui/enums/tooltip-placement.enum';

import './Tooltip.css';

interface TooltipProps {
  /** The hint; it repeats text the trigger already exposes (its name or full text), so it is hidden from assistive technology. */
  content: ReactNode;
  /** Where the bubble sits relative to the trigger. */
  placement?: TooltipPlacement;
  /** Stretch the wrapper to its container (e.g. a truncated name in a card). */
  isBlock?: boolean;
  /** The trigger: a focusable control, or text inside one. */
  children: ReactNode;
}

/**
 * A short visual hint on hover and keyboard focus (WCAG 1.4.13): it appears after a delay, stays
 * while the pointer is over it, and Escape dismisses it without moving focus.
 */
export const Tooltip = ({
  content,
  placement = TooltipPlacement.Top,
  isBlock = false,
  children,
}: TooltipProps): ReactElement => {
  const [isDismissed, setIsDismissed] = useState(false);
  const classes = [
    'tooltip',
    `tooltip--${placement}`,
    isBlock ? 'tooltip--block' : '',
    isDismissed ? 'tooltip--dismissed' : '',
  ];
  return (
    // The wrapper only listens: Escape on the trigger inside hides the bubble (1.4.13 dismissible).
    // eslint-disable-next-line jsx-a11y-x/no-static-element-interactions -- not a control itself; the trigger inside is
    <span
      className={classes.filter(Boolean).join(' ')}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && !isDismissed) setIsDismissed(true);
      }}
      onPointerLeave={() => setIsDismissed(false)}
      onBlur={() => setIsDismissed(false)}
    >
      {children}
      <span className="tooltip__bubble" role="tooltip" aria-hidden="true">
        {content}
      </span>
    </span>
  );
};
