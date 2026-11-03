import type { ButtonHTMLAttributes, ReactElement, ReactNode } from 'react';

import { ButtonVariant } from '#ui/enums/button-variant.enum';

import './Button.css';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  children: ReactNode;
}

/** The one button: primary actions get the 44 px target, the rest at least 24 px. */
export const Button = ({
  variant = ButtonVariant.Primary,
  className,
  type = 'button',
  children,
  ...rest
}: ButtonProps): ReactElement => (
  <button
    {...rest}
    type={type}
    className={['button', `button--${variant}`, className].filter(Boolean).join(' ')}
  >
    {children}
  </button>
);
