import type { ButtonHTMLAttributes, ReactElement, ReactNode, Ref } from 'react';

import { ButtonVariant } from '#ui/enums/button-variant.enum';

import './Button.css';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Primary for the main action of a view (44 px target), secondary or ghost for the rest (36 px). */
  variant?: ButtonVariant;
  /** A leading icon (decorative: the label names the action). */
  icon?: ReactNode;
  /** The action in a verb or short phrase. */
  children: ReactNode;
  /** The DOM button, e.g. to move focus back to it. */
  ref?: Ref<HTMLButtonElement> | undefined;
}

interface ButtonClassNameProps {
  variant?: ButtonVariant;
  className?: string | undefined;
}

/** The button's class names, for a link that looks like a button (e.g. a router `Link`). */
export const buttonClassName = ({
  variant = ButtonVariant.Primary,
  className,
}: ButtonClassNameProps = {}): string =>
  ['button', `button--${variant}`, className].filter(Boolean).join(' ');

/** The one button: primary actions get the 44 px target, the rest 36 px (at least 24 px). */
export const Button = ({
  variant = ButtonVariant.Primary,
  icon,
  className,
  type = 'button',
  children,
  ...rest
}: ButtonProps): ReactElement => (
  <button {...rest} type={type} className={buttonClassName({ variant, className })}>
    {icon ? (
      <span className="button__icon" aria-hidden="true">
        {icon}
      </span>
    ) : null}
    {children}
  </button>
);
