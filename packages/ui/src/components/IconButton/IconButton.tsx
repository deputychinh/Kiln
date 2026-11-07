import type { ButtonHTMLAttributes, ReactElement, ReactNode, Ref } from 'react';

import { Tooltip } from '#ui/components/Tooltip/Tooltip';
import { ButtonVariant } from '#ui/enums/button-variant.enum';
import { IconButtonSize } from '#ui/enums/icon-button-size.enum';
import { TooltipPlacement } from '#ui/enums/tooltip-placement.enum';

import './IconButton.css';

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  /** Names the button for assistive technology and shows as its tooltip. */
  label: string;
  /** The icon (decorative: the label names the action). */
  icon: ReactNode;
  /** Ghost by default; secondary for a bordered control, primary for the main action. */
  variant?: ButtonVariant;
  /** Small 32 px (dense toolbars), medium 36 px, large 44 px (primary or touch-first). */
  size?: IconButtonSize;
  /** A toggle's state, announced as pressed / not pressed. */
  isPressed?: boolean;
  /** Where the tooltip shows. */
  tooltipPlacement?: TooltipPlacement;
  /** The DOM button, e.g. to move focus back to it. */
  ref?: Ref<HTMLButtonElement> | undefined;
}

/** A square button that is only an icon; its label is the accessible name and the tooltip. */
export const IconButton = ({
  label,
  icon,
  variant = ButtonVariant.Ghost,
  size = IconButtonSize.Medium,
  isPressed,
  tooltipPlacement = TooltipPlacement.Bottom,
  className,
  type = 'button',
  ...rest
}: IconButtonProps): ReactElement => (
  <Tooltip content={label} placement={tooltipPlacement}>
    <button
      {...rest}
      type={type}
      aria-label={label}
      aria-pressed={isPressed}
      className={['icon-button', `icon-button--${variant}`, `icon-button--${size}`, className]
        .filter(Boolean)
        .join(' ')}
    >
      <span className="icon-button__icon" aria-hidden="true">
        {icon}
      </span>
    </button>
  </Tooltip>
);
